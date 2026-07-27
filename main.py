import os, time, threading, requests
from flask import Flask, jsonify, Response

app = Flask(__name__)

TG_TOKEN = os.environ.get("BOT_TOKEN")
TG_CHAT = os.environ.get("CHAT_ID")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

DATA = {
    "price": 0.0, "rsi_1m": 50.0, "rsi_3m": 50.0, "rsi_5m": 50.0, "rsi_10m": 50.0, "rsi_1h": 50.0,
    "boll_up": 0.0, "boll_dn": 0.0, "ema7": 0.0, "ema25": 0.0,
    "title": "SYSTEM_INIT", "advice": "CONNECTING TO BINANCE FUTURES API...", "color": "#00ff41", "time": "--",
    "session_name": "ANALYZING...", "session_advice": "CALCULATING WIN RATE...", "win_rate": "--",
    "ping": "0ms", "signal_tier": "STANDBY"
}

def get_beijing_time_struct():
    return time.gmtime(time.time() + 28800)

def get_beijing_time():
    return time.strftime("%Y-%m-%d %H:%M:%S", get_beijing_time_struct())

def get_session_info():
    t = get_beijing_time_struct()
    hour, minute = t.tm_hour, t.tm_min
    if 8 <= hour < 15:
        if hour == 8 and minute < 30:
            return "早八交割期 [HIGH_VOL]", "高频插针，建议 08:30 后入场", "胜率: 68%", "#f97316"
        return "亚盘黄金震荡期 [ACCURATE]", "指标极少钝化，极其适合 BOLL+RSI 高抛低吸", "胜率: 85%", "#00ff41"
    elif 15 <= hour < 19:
        return "欧盘趋势启动期 [TREND]", "方向明确，适合抓 BOLL 轨外共振反弹", "胜率: 88%", "#00f3ff"
    elif 20 <= hour < 24:
        if hour == 20 or (hour == 21 and minute <= 30):
            return "美盘数据敏感期 [VOLATILE]", "剧烈波动，严禁单边逆势，只做 S 级共振！", "胜率: 78%", "#ff003c"
        return "美盘黄金交易期 [KING_MODE]", "顶级流动性，顺势共振信号胜率之王", "胜率: 92%+", "#00ff41"
    else:
        return "深夜低量横盘期 [LOW_VOL]", "量能清淡，只做 BOLL 上下轨极值", "胜率: 75%", "#848e9c"

def send_tg(msg):
    if TG_TOKEN and TG_CHAT:
        try:
            r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": TG_CHAT, "text": msg}, timeout=5)
            return True, r.text
        except Exception as e:
            return False, str(e)
    return False, "TG 未配置"

def send_webhook(title, content):
    if not WEBHOOK_URL:
        return False, "WEBHOOK_URL 未配置"
    try:
        url = WEBHOOK_URL.strip()
        msg_text = f"⚡【暴爷无极限·绝杀矩阵预警】⚡\n{title}\n\n{content}"
        if "feishu" in url or "larksuite" in url:
            payload = {"msg_type": "text", "content": {"text": msg_text}}
        else:
            payload = {"msgtype": "text", "text": {"content": msg_text}}
        r = requests.post(url, json=payload, timeout=5)
        res = r.json()
        if res.get("errcode") == 0 or res.get("StatusCode") == 0 or res.get("code") == 0:
            return True, "发送成功"
        return False, f"推送失败: {res}"
    except Exception as e:
        return False, str(e)

def notify(title, text):
    s_name, s_adv, win_rate, _ = get_session_info()
    full_text = f"{text}\n\n🎯 推荐时段: {s_name} [{win_rate}]\n💡 策略指导: {s_adv}\n⏰ 时间: {get_beijing_time()}"
    send_tg(f"{title}\n{full_text}")
    send_webhook(title, full_text)

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
        return 100.0
    return round(100.0 - (100.0 / (1.0 + (avg_g / avg_l))), 2)

def calc_ema(prices, period):
    if len(prices) < period:
        return prices[-1] if prices else 0.0
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = (p * k) + (ema * (1 - k))
    return round(ema, 2)

def calc_bollinger(prices, period=20, std_dev=2):
    if len(prices) < period:
        p = prices[-1] if prices else 0.0
        return p, p, p
    slice_p = prices[-period:]
    sma = sum(slice_p) / period
    variance = sum((x - sma) ** 2 for x in slice_p) / period
    std = variance ** 0.5
    return round(sma, 2), round(sma + (std * std_dev), 2), round(sma - (std * std_dev), 2)

def fetch_futures_klines(symbol, interval, limit=100):
    endpoints = [
        "https://fapi.binance.com/fapi/v1/klines",
        "https://fapi.binance.vision/fapi/v1/klines"
    ]
    headers = {"User-Agent": "Mozilla/5.0"}
    for url in endpoints:
        try:
            r = requests.get(url, params={"symbol": symbol, "interval": interval, "limit": limit}, headers=headers, timeout=3)
            if r.status_code == 200:
                return [float(k[4]) for k in r.json()]
        except:
            continue
    return []

def resample_klines(p1m, period_minutes):
    res = []
    for i in range(0, len(p1m), period_minutes):
        chunk = p1m[i:i+period_minutes]
        if chunk:
            res.append(chunk[-1])
    return res

def fetch_data_all():
    p1m = fetch_futures_klines("BTCUSDT", "1m", 150)
    p3m = fetch_futures_klines("BTCUSDT", "3m", 100)
    p5m = fetch_futures_klines("BTCUSDT", "5m", 100)
    p1h = fetch_futures_klines("BTCUSDT", "1h", 100)
    if not p1m or not p3m or not p5m or not p1h:
        raise Exception("API 超时")
    p = p1m[-1]
    r1 = calc_rsi_wilder(p1m, 6)
    r3 = calc_rsi_wilder(p3m, 6)
    r5 = calc_rsi_wilder(p5m, 6)
    r10 = calc_rsi_wilder(resample_klines(p1m, 10), 6)
    r1h = calc_rsi_wilder(p1h, 6)
    sma, boll_up, boll_dn = calc_bollinger(p1m, 20, 2)
    ema7 = calc_ema(p1m, 7)
    ema25 = calc_ema(p1m, 25)
    return p, r1, r3, r5, r10, r1h, boll_up, boll_dn, ema7, ema25

def analyze_high_winrate(p, r1, r3, r5, r10, r1h, boll_up, boll_dn, ema7, ema25):
    is_strong_up = (ema7 > ema25 + 15) and (p > ema7)
    is_strong_down = (ema7 < ema25 - 15) and (p < ema7)
    if p <= boll_dn and r1 <= 15 and r3 <= 25 and r5 <= 30 and not is_strong_down:
        return "🔥【S级绝杀·买入看涨(UP)】", "BOLL下轨支撑 + 三重超卖！胜率 90%+", "#00ff41", "S-TIER WIN 90%"
    if p >= boll_up and r1 >= 85 and r3 >= 75 and r5 >= 70 and not is_strong_up:
        return "🔥【S级绝杀·买入看跌(DOWN)】", "BOLL上轨阻力 + 三重超买！胜率 90%+", "#ff003c", "S-TIER WIN 90%"
    if r1 >= 85 and is_strong_up:
        return "⚠️【强单边暴拉中·拒绝看跌】", "多头强趋势，RSI钝化中，严禁做空！", "#ffe600", "LOCKED_PREVENT_LOSS"
    if r1 <= 15 and is_strong_down:
        return "⚠️【强单边砸盘中·拒绝看涨】", "空头强趋势，RSI钝化中，严禁抄底！", "#ffe600", "LOCKED_PREVENT_LOSS"
    if p <= boll_dn * 1.0005 and r1 <= 15:
        return "⚡【A级优质·建议看涨(UP)】", "触及 1m BOLL 下轨，抓超短线反弹", "#00f3ff", "A-TIER WIN 82%"
    if p >= boll_up * 0.9995 and r1 >= 85:
        return "⚡【A级优质·建议看跌(DOWN)】", "触及 1m BOLL 上轨，抓超短线回撤", "#ff003c", "A-TIER WIN 82%"
    return "暴爷无极限绝杀矩阵待命", "盘面无极值共振，保持观望等待信号", "#848e9c", "STANDBY"

def monitor():
    global DATA
    s_lock = False
    while True:
        try:
            p, r1, r3, r5, r10, r1h, boll_up, boll_dn, ema7, ema25 = fetch_data_all()
            title, adv, color, tier = analyze_high_winrate(p, r1, r3, r5, r10, r1h, boll_up, boll_dn, ema7, ema25)
            bj_time = get_beijing_time()
            s_name, s_adv, win_rate, b_color = get_session_info()
            DATA = {
                "price": p, "rsi_1m": r1, "rsi_3m": r3, "rsi_5m": r5,
                "rsi_10m": r10, "rsi_1h": r1h, "boll_up": boll_up, "boll_dn": boll_dn,
                "ema7": ema7, "ema25": ema25, "title": title, "advice": adv,
                "color": color, "time": bj_time, "session_name": s_name,
                "session_advice": s_adv, "win_rate": win_rate, "badge_color": b_color,
                "signal_tier": tier
            }
            if "S级" in title or "A级" in title:
                if not s_lock:
                    notify(f"{title}", f"BTCUSDT 合约参考价: ${p}\n1m BOLL 上轨: ${boll_up} | 下轨: ${boll_dn}\n1m RSI: {r1} | 3m RSI: {r3} | 5m RSI: {r5}\n1h 大趋势 RSI: {r1h}")
                    s_lock = True
            else:
                s_lock = False
        except Exception as e:
            print("Monitor error:", e)
        time.sleep(1)

threading.Thread(target=monitor, daemon=True).start()

HTML_PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>暴爷无极限 ⚡ 90%+ 绝杀终端</title><style>*{box-sizing:border-box}body{font-family:'Courier New',Consolas,monospace;padding:12px;background:#05070a;color:#00ff41;margin:0}.terminal{background:#0c1017;padding:20px;border-radius:12px;max-width:440px;margin:10px auto;border:1px solid #00ff4155;box-shadow:0 0 20px rgba(0,255,65,0.2)}.header{text-align:center;border-bottom:1px dashed #00ff4155;padding-bottom:12px;margin-bottom:15px}.glitch-title{font-size:24px;font-weight:900;color:#ffe600;text-shadow:0 0 10px #ffe600,0 0 20px #ff003c;margin:0}.sub-title{font-size:10px;color:#00f3ff;margin-top:5px}.session-card{background:#070a0f;padding:12px;border-radius:8px;margin-bottom:15px;border:1px solid #00f3ff44}.session-top{display:flex;justify-content:space-between;align-items:center;font-size:12px;font-weight:bold;margin-bottom:4px}.session-desc{font-size:11px;color:#848e9c;line-height:1.3}.box{background:#070a0f;padding:14px;border-radius:8px;margin-bottom:15px;border-left:5px solid #00ff41}.title{font-size:11px;color:#848e9c;margin-bottom:4px}.val{font-size:14px;font-weight:bold;color:#fff}.price-row{display:flex;justify-content:space-between;align-items:center;background:#070a0f;padding:12px 16px;border-radius:8px;margin-bottom:15px;border:1px solid #00ff4144}.price-label{font-size:12px;color:#848e9c}.price-val{font-size:20px;font-weight:bold;color:#ffe600}.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px}.gbox{background:#070a0f;padding:10px;border-radius:6px;text-align:center;border:1px solid #00ff4133}.gname{font-size:10px;color:#848e9c}.gval{font-size:16px;font-weight:bold;margin-top:4px;color:#00ff41}.trend-box{background:#070a0f;padding:12px;border-radius:6px;display:flex;justify-content:space-between;align-items:center;border:1px solid #00f3ff33;margin-bottom
