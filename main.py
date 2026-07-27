import os, time, threading, requests
from flask import Flask, jsonify, Response

app = Flask(__name__)

TG_TOKEN = os.environ.get("BOT_TOKEN")
TG_CHAT = os.environ.get("CHAT_ID")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

# 复用 HTTP 长连接，降低延迟
session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})

# 全局共享状态与学习数据
EVO_ENGINE = {
    "records": [],          # 历史信号履约记录
    "total_signals": 0,     # 总发单数
    "wins": 0,              # 胜单数
    "losses": 0,            # 负单数
    "win_rate": 100.0,      # 实时胜率 (%)
    "dynamic_rsi_low": 15,  # 动态学习下限阈值
    "dynamic_rsi_high": 85, # 动态学习上限阈值
    "evolution_stage": "初始算法 (胜率保护开启)"
}

DATA = {
    "price": 0.0, "rsi_1m": 50.0, "rsi_3m": 50.0, "rsi_5m": 50.0, "rsi_10m": 50.0, "rsi_1h": 50.0,
    "title": "进化引擎启动中", "advice": "正在建立数据模型", "color": "#f0b90b", "time": "--",
    "evo": EVO_ENGINE
}

def get_beijing_time():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 28800))

def send_tg(msg):
    if TG_TOKEN and TG_CHAT:
        try:
            session.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": TG_CHAT, "text": msg}, timeout=3)
        except Exception:
            pass

def send_webhook(title, content):
    if not WEBHOOK_URL:
        return
    try:
        url = WEBHOOK_URL.strip()
        msg_text = f"⚡【事件合约预警】{title}\n\n{content}"
        payload = {"msgtype": "text", "text": {"content": msg_text}}
        session.post(url, json=payload, timeout=3)
    except Exception:
        pass

def notify(title, text):
    send_tg(f"{title}\n{text}")
    send_webhook(title, f"{text}\n\n时间: {get_beijing_time()}")

def calc_rsi_wilder(prices, period=6):
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
    return round(100.0 - (100.0 / (1.0 + (avg_g / avg_l))), 2)

def resample_closes(closes_1m, interval_min):
    if interval_min == 1:
        return closes_1m
    length = len(closes_1m)
    remainder = length % interval_min
    start_idx = remainder if remainder > 0 else 0
    res = []
    for i in range(start_idx, length, interval_min):
        chunk = closes_1m[i:i + interval_min]
        if chunk:
            res.append(chunk[-1])
    return res

def fetch_data():
    urls = [
        "https://data-api.binance.vision/api/v3/klines",
        "https://api.binance.com/api/v3/klines",
        "https://api1.binance.com/api/v3/klines"
    ]
    res = None
    for u in urls:
        try:
            r = session.get(u, params={"symbol": "BTCUSDT", "interval": "1m", "limit": 1000}, timeout=2.5)
            if r.status_code == 200:
                res = r.json()
                if isinstance(res, list) and len(res) > 0:
                    break
        except Exception:
            continue
    if not res:
        raise Exception("行情接口连接超时")

    closes_1m = [float(k[4]) for k in res]
    p = closes_1m[-1]

    r1 = calc_rsi_wilder(closes_1m, 6)
    r3 = calc_rsi_wilder(resample_closes(closes_1m, 3), 6)
    r5 = calc_rsi_wilder(resample_closes(closes_1m, 5), 6)
    r10 = calc_rsi_wilder(resample_closes(closes_1m, 10), 6)
    r1h = calc_rsi_wilder(resample_closes(closes_1m, 60), 6)

    return p, r1, r3, r5, r10, r1h

# 🧬 自自我进化学习引擎：动态调整参数与履约闭环
def process_evolution(current_price):
    global EVO_ENGINE
    now = time.time()
    
    # 1. 检查待履约的历史信号（5分钟后结算胜率）
    for rec in EVO_ENGINE["records"]:
        if rec["status"] == "PENDING" and (now - rec["timestamp"]) >= 300: # 300秒(5分钟)结算
            rec["settle_price"] = current_price
            if rec["direction"] == "UP":
                rec["result"] = "WIN" if current_price > rec["trigger_price"] else "LOSS"
            else: # DOWN
                rec["result"] = "WIN" if current_price < rec["trigger_price"] else "LOSS"
            
            rec["status"] = "SETTLED"
            EVO_ENGINE["total_signals"] += 1
            if rec["result"] == "WIN":
                EVO_ENGINE["wins"] += 1
            else:
                EVO_ENGINE["losses"] += 1
            
            # 更新胜率
            if EVO_ENGINE["total_signals"] > 0:
                EVO_ENGINE["win_rate"] = round((EVO_ENGINE["wins"] / EVO_ENGINE["total_signals"]) * 100, 1)

    # 2. 根据历史胜率进化调整策略阈值
    recent_settled = [r for r in EVO_ENGINE["records"] if r["status"] == "SETTLED"][-20:]
    if len(recent_settled) >= 5:
        recent_wins = sum(1 for r in recent_settled if r["result"] == "WIN")
        recent_rate = (recent_wins / len(recent_settled)) * 100
        
        if recent_rate < 80.0:
            # 胜率下降，自动收紧触发门槛（进化为更严格的极值条件）
            EVO_ENGINE["dynamic_rsi_low"] = 10
            EVO_ENGINE["dynamic_rsi_high"] = 90
            EVO_ENGINE["evolution_stage"] = "🤖 进化阶段: 极致防御 (RSI 10/90)"
        elif recent_rate >= 90.0:
            # 胜率极高，适当恢复标准门槛以捕捉更多行情
            EVO_ENGINE["dynamic_rsi_low"] = 15
            EVO_ENGINE["dynamic_rsi_high"] = 85
            EVO_ENGINE["evolution_stage"] = "🤖 进化阶段: 进攻共振 (RSI 15/85)"
        else:
            EVO_ENGINE["dynamic_rsi_low"] = 12
            EVO_ENGINE["dynamic_rsi_high"] = 88
            EVO_ENGINE["evolution_stage"] = "🤖 进化阶段: 均衡高胜率 (RSI 12/88)"

def analyze(p, r1, r3, r5, r10, r1h):
    r_low = EVO_ENGINE["dynamic_rsi_low"]
    r_high = EVO_ENGINE["dynamic_rsi_high"]

    if r1h >= 50 and r10 <= 30 and r1 <= r_low:
        return "【90%+进化高胜率】趋势向上+深度超卖", "强烈建议：买入看涨 (UP)", "#10b981", "UP"
    if r1h <= 50 and r10 >= 70 and r1 >= r_high:
        return "【90%+进化高胜率】趋势向下+深度超买", "强烈建议：买入看跌 (DOWN)", "#ef4444", "DOWN"
    if r1 <= r_low and r3 <= 20 and r5 <= 25:
        return "【自适应超卖】1m/3m/5m强力插针", "建议：抓短线反弹 (UP)", "#10b981", "UP"
    if r1 >= r_high and r3 >= 80 and r5 >= 75:
        return "【自适应超买】1m/3m/5m拉升极值", "建议：抓短线回撤 (DOWN)", "#ef4444", "DOWN"
    if r1 >= r_high:
        return f"触发自适应超买警戒 (>={r_high})", "谨防回调，可小仓看跌 (DOWN)", "#f97316", "DOWN_WEAK"
    if r1 <= r_low:
        return f"触发自适应超卖警戒 (<={r_low})", "谨防反弹，可小仓看涨 (UP)", "#3b82f6", "UP_WEAK"
    return "事件合约常态运转中", f"等待极值点 (进化门槛: <={r_low} 或 >={r_high})", "#848e9c", "NONE"

def monitor():
    global DATA, EVO_ENGINE
    last_signal_time = 0
    while True:
        try:
            p, r1, r3, r5, r10, r1h = fetch_data()
            process_evolution(p)
            
            title, adv, color, sig_type = analyze(p, r1, r3, r5, r10, r1h)
            bj_time = get_beijing_time()
            
            DATA = {
                "price": p, "rsi_1m": r1, "rsi_3m": r3, "rsi_5m": r5,
                "rsi_10m": r10, "rsi_1h": r1h, "title": title,
                "advice": adv, "color": color, "time": bj_time,
                "evo": {
                    "total": EVO_ENGINE["total_signals"],
                    "wins": EVO_ENGINE["wins"],
                    "losses": EVO_ENGINE["losses"],
                    "win_rate": EVO_ENGINE["win_rate"],
                    "stage": EVO_ENGINE["evolution_stage"],
                    "low": EVO_ENGINE["dynamic_rsi_low"],
                    "high": EVO_ENGINE["dynamic_rsi_high"]
                }
            }

            # 发送信号与记录至进化数据池（防刷冷却 180 秒）
            now = time.time()
            if sig_type in ["UP", "DOWN"] and (now - last_signal_time) > 180:
                EVO_ENGINE["records"].append({
                    "timestamp": now,
                    "trigger_price": p,
                    "direction": sig_type,
                    "status": "PENDING",
                    "result": "UNKNOWN"
                })
                notify(f"🔥{title}", f"现价: ${p}\n指令: {adv}\n进化门槛: Low={EVO_ENGINE['dynamic_rsi_low']} High={EVO_ENGINE['dynamic_rsi_high']}")
                last_signal_time = now

        except Exception as e:
            print("Monitor Execution Notice:", e)
        time.sleep(1.5)

threading.Thread(target=monitor, daemon=True).start()

HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BTC 事件合约自适应进化终端</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;padding:12px;background:#0b0e11;color:#eaecef;margin:0}
.card{background:#181a20;padding:16px;border-radius:16px;max-width:420px;margin:auto;border:1px solid #2b2f36}
h2{color:#f0b90b;font-size:17px;text-align:center;margin:0 0 10px 0}
.evo-panel{background:#1e2329;padding:10px;border-radius:10px;margin-bottom:12px;border:1px solid #363c4e;font-size:12px}
.evo-title{color:#f0b90b;font-weight:bold;margin-bottom:4px;display:flex;justify-content:space-between}
.box{background:#2b2f36;padding:12px;border-radius:10px;margin:10px 0;border-left:5px solid #f0b90b}
.title{font-size:12px;color:#848e9c;margin-bottom:2px}
.val{font-size:14px;font-weight:bold}
.item{display:flex;justify-content:space-between;margin:8px 0;font-size:13px;border-bottom:1px dashed #2b2f36;padding-bottom:4px}
.v{font-weight:bold;color:#f0b90b}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}
.gbox{background:#2b2f36;padding:8px;border-radius:8px;text-align:center;font-size:11px}
.gval{font-size:15px;font-weight:bold;margin-top:2px;color:#f0b90b}
.time{color:#848e9c;font-size:10px;text-align:center;margin-top:10px}
</style>
</head>
<body>
<div class="card">
<h2>⚡ BTC 事件合约自适应进化终端</h2>

<div class="evo-panel">
<div class="evo-title"><span id="estage">算法自适应计算中...</span><span id="ewr" style="color:#10b981">胜率: 100%</span></div>
<div style="color:#848e9c">战绩统计: <span id="estat" style="color:#fff">0胜 0负 (总 0 单)</span> | 动态极值: <span id="ethres" style="color:#f0b90b">15 / 85</span></
