import requests

# 1. 常驻 HTTP Session，复用 TCP 握手长连接，大幅降低请求延迟
session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})

def calc_rsi_wilder(prices, period=6):
    """采用 Wilder Smoothing 平滑算法计算 RSI 指标（含边界极限保护）"""
    if len(prices) < period + 1:
        return 50.0
    
    gains, losses = [], []
    for i in range(1, len(prices)):
        d = prices[i] - prices[i-1]
        gains.append(d if d > 0 else 0.0)
        losses.append(abs(d) if d < 0 else 0.0)
        
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    
    for i in range(period, len(gains)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
        
    if avg_l == 0:
        return 100.0 if avg_g > 0 else 50.0
        
    rs = avg_g / avg_l
    return round(100.0 - (100.0 / (1.0 + rs)), 2)

def resample_closes(closes_1m, interval_min):
    """
    将 1m 连续收盘价重采样为指定分钟周期的收盘价数组
    interval_min: 3, 5, 10, 60
    """
    if interval_min == 1:
        return closes_1m
        
    # 从最新一根倒推分组，确保最新 1m 收盘价永远落入当前最新的大周期 K 线内
    length = len(closes_1m)
    remainder = length % interval_min
    start_idx = remainder if remainder > 0 else 0
    
    res = []
    for i in range(start_idx, length, interval_min):
        chunk = closes_1m[i:i + interval_min]
        if chunk:
            res.append(chunk[-1])  # 提取该周期的收盘价
    return res

def fetch_data():
    """极速多线路故障转移与数据合成"""
    urls = [
        "https://data-api.binance.vision/api/v3/klines",
        "https://api.binance.com/api/v3/klines",
        "https://api1.binance.com/api/v3/klines"
    ]
    
    res = None
    for u in urls:
        try:
            # 利用复用的 session 发起极速请求
            r = session.get(u, params={"symbol": "BTCUSDT", "interval": "1m", "limit": 1000}, timeout=2.5)
            if r.status_code == 200:
                res = r.json()
                if isinstance(res, list) and len(res) > 0:
                    break
        except Exception:
            continue
            
    if not res:
        raise Exception("所有数据源连接超时")

    # 提取 1m 收盘价数组
    closes_1m = [float(k[4]) for k in res]
    current_price = closes_1m[-1]

    # 内存级秒级重采样与 RSI(6) 计算
    r1 = calc_rsi_wilder(closes_1m, 6)
    r3 = calc_rsi_wilder(resample_closes(closes_1m, 3), 6)
    r5 = calc_rsi_wilder(resample_closes(closes_1m, 5), 6)
    r10 = calc_rsi_wilder(resample_closes(closes_1m, 10), 6)
    r1h = calc_rsi_wilder(resample_closes(closes_1m, 60), 6)

    return current_price, r1, r3, r5, r10, r1h
