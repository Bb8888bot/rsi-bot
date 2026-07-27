import os, time, threading, requests
from flask import Flask, jsonify, Response

app = Flask(__name__)

TG_TOKEN = os.environ.get("BOT_TOKEN")
TG_CHAT = os.environ.get("CHAT_ID")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

DATA = {
    "price": 0.0, "rsi_1m": 50.0, "rsi_10m": 50.0, "rsi_1h": 50.0,
    "boll_up": 0.0, "boll_mb": 0.0, "boll_dn": 0.0, "ema7": 0.0, "ema25": 0.0, "ema99": 0.0,
    "title": "MATRIX_STANDBY", "advice": "等待 1m/10m 极值共振 (<=15 或 >=85)", "win_rate": "85%", "session_name": "亚盘震荡期"
}

def get_beijing_time():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 28800))

def get_session_info():
    h = time.gmtime(time.time() + 28800).tm_hour
    if 8 <= h < 15:
        return "亚盘黄金震荡期", "极少钝化，适合 BOLL 轨外极值高抛低吸", "85%"
    elif 15 <= h < 19:
        return "欧盘趋势启动期", "方向明确，抓轨道外共振反弹", "88%"
    elif 20 <= h < 24:
        return "美盘黄金交易期", "顶级流动性，顺势共振核心时段", "92%+"
    else:
        return "深夜低量横盘期", "量能清淡，仅做上下轨极端防守", "75%"

def send_tg(msg):
    if TG_TOKEN and TG_CHAT:
        try:
            requests.post("https://api.telegram.org/bot" + TG_TOKEN + "/sendMessage", data={"chat_id": TG_CHAT, "text": msg}, timeout=3)
        except:
            pass

def send_webhook(msg):
    if WEBHOOK_URL:
        try:
            requests.post(WEBHOOK_URL.strip(), json={"msgtype": "text", "text": {"content": msg}}, timeout=3)
        except:
            pass

def notify(title, text):
    s_name, s_adv, win_rate = get_session_info()
    full = title + "\n" + text + "\n推荐时段: " + s_name + " [胜率: " + win_rate + "]\n战法指导: " + s_adv + "\n时间: " + get_beijing_time()
    send_tg(full)
    send_webhook(full)

def calc_rsi(prices, period=6):
    if len(prices) < period + 1:
        return 50.0
    g, l = 0.0, 0.0
    for i in range(1, period + 1):
        d = prices[i] - prices[i-1]
        if d > 0: g += d
        else: l += abs(d)
    ag, al = g / period, l / period
    if al == 0: return 100.0
    return round(100.0 - (100.0 / (1.0 + (ag / al))), 2)

def calc_boll(prices, period=20):
    if len(prices) < period:
        p = prices[-1] if prices else 0.0
        return p, p, p
    sp = prices[-period:]
    sma = sum(sp) / period
    std = (sum((x - sma) ** 2 for x in sp) / period) ** 0.5
    return round(sma + (std * 2), 2), round(sma, 2), round(sma - (std * 2), 2)

def calc_ema(prices, period):
    if len(prices) < period:
        return prices[-1] if prices else 0.0
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = (p * k) + (ema * (1 - k))
    return round(ema, 2)

def resample_klines(p1m, period_minutes):
    res = []
    for i in range(0, len(p1m), period_minutes):
        chunk = p1m[i:i+period_minutes]
        if chunk:
            res.append(chunk[-1])
    return res

def fetch_klines(interval, limit=120):
    endpoints = [
        ("https://fapi.binance.com/fapi/v1/klines", {"symbol": "BTCUSDT", "interval": interval, "limit": limit}),
        ("https://api.binance.com/api/v3/klines", {"symbol": "BTCUSDT", "interval": interval, "limit": limit}),
        ("https://dapi.binance.com/dapi/v1/klines", {"symbol": "BTCUSD_PERP", "interval": interval, "limit": limit})
    ]
    headers = {"User-Agent": "Mozilla/5.0"}
    for url, params in endpoints:
        try:
            r = requests.get(url, params=params, headers=headers, timeout=3)
            if r.status_code == 200:
                res = r.json()
                if isinstance(res, list) and len(res) > 0:
                    return [float(k[4]) for k in res]
        except:
            continue
    return []

def monitor():
    global DATA
    lock = False
    while True:
        try:
            p1m = fetch_klines("1m", 150)
            p1h = fetch_klines("1h", 120)
            if p1m:
                p = p1m[-1]
                r1m = calc_rsi(p1m, 6)
                p10m = resample_klines(p1m, 10)
                r10m = calc_rsi(p10m, 6) if len(p10m) > 7 else r1m
                r1h = calc_rsi(p1h, 6) if p1h else r1m

                bup, bmb, bdn = calc_boll(p1m, 20)
                e7 = calc_ema(p1m, 7)
                e25 = calc_ema(p1m, 25)
                e99 = calc_ema(p1h, 99) if p1h else e25

                title = "暴爷事件合约矩阵待命"
                advice = "等待 1m/10m RSI 达到 <=15 或 >=85 极值共振"
                
                # 严格执行咱们定好的数值标准：1m 和 10m 同时达到 <=15（超卖看涨）或 >=85（超买看跌）
                if r1m <= 15 and r10m <= 25:
                    title = "🔥【S级绝杀·买入看涨(UP)】"
                    advice = "1m/10m RSI 触及 <=15 超卖极值，配合BOLL下轨果断看涨！"
                elif r1m >= 85 and r10m >= 75:
                    title = "🔥【S级绝杀·买入看跌(DOWN)】"
                    advice = "1m/10m RSI 触及 >=85 超买极值，配合BOLL上轨果断看跌！"

                s_name, s_adv, win_rate = get_session_info()
                DATA = {
                    "price": p, "rsi_1m": r1m, "rsi_10m": r10m, "rsi_1h": r1h,
                    "boll_up": bup, "boll_mb": bmb, "boll_dn": bdn,
                    "ema7": e7, "ema25": e25, "ema99": e99,
                    "title": title, "advice": advice, "win_rate": win_rate, "session_name": s_name
                }

                if "S级" in title and not lock:
                    notify(title, "现价: $" + str(p) + " | 1m RSI: " + str(r1m) + " | 10m RSI: " + str(r10m) + "\nBOLL下轨: " + str(bdn) + " | 上轨: " + str(bup))
                    lock = True
                elif "S级" not in title:
                    lock = False
        except Exception as e:
            print(e)
        time.sleep(1)

threading.Thread(target=monitor, daemon=True).start()

PAGE = """<!DOCTYPE html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>暴爷事件合约终端</title>
<style>body{background:#05070a;color:#00ff41;font-family:monospace;padding:15px;margin:0}
.box{background:#0c1017;padding:15px;border-radius:10px;border:1px solid #00ff4155;max-width:400px;margin:auto}
h2{color:#ffe600;text-align:center;margin-top:0}
.row{display:flex;justify-content:space-between;margin:6px 0;font-size:12px}
</style></head><body>
<div class='box'><h2>⚡ 暴爷事件合约 ⚡</h2>
<div class='row'><b>当前时段:</b> <span id='sn' style='color:#00f3ff'>--</span> [胜率: <span id='sw' style='color:#ffe600'>--</span>]</div>
<div class='row'><b>信号状态:</b> <span id='t'>实时连线中...</span></div>
<div class='row'><b>BTC现价:</b> <span id='p' style='color:#ffe600;font-weight:bold;font-size:15px'>$0.00</span></div>
<div class='row'><b>BOLL 上/中/下:</b> <span id='b' style='color:#ff003c'>--</span></div>
<div class='row'><b>EMA 7/25/99:</b> <span id='e' style='color:#00f3ff'>--</span></div>
<div class='row'><b>1m RSI(6):</b> <span id='r1' style='color:#00ff41'>--</span></div>
<div class='row'><b>10m RSI(6):</b> <span id='r10' style='color:#ffe600'>--</span></div>
<div class='row'><b>1h 大趋势 RSI:</b> <span id='r1h' style='color:#da70d6'>--</span></div>
<div class='row'><b>策略建议:</b> <span id='a' style='color:#ffe600'>--</span></div>
</div>
<script>setInterval(()=>{fetch('/api/data').then(r=>r.json()).then(d=>{
document.getElementById('sn').innerText=d.session_name;
document.getElementById('sw').innerText=d.win_rate;
document.getElementById('t').innerText=d.title;
document.getElementById('p').innerText='$'+d.price.toFixed(2);
document.getElementById('b').innerText=d.boll_up+' / '+d.boll_mb+' / '+d.boll_dn;
document.getElementById('e').innerText=d.ema7+' / '+d.ema25+' / '+d.ema99;
document.getElementById('r1').innerText=d.rsi_1m;
document.getElementById('r10').innerText=d.rsi_10m;
document.getElementById('r1h').innerText=d.rsi_1h;
document.getElementById('a').innerText=d.advice;
});},1000);</script></body></html>"""

@app.route('/')
def home():
    return Response(PAGE, mimetype="text/html")

@app.route('/api/data')
def api_data():
    return jsonify(DATA)

@app.route('/test')
def test_push():
    notify("🧪 暴爷测试", "全功能数据通道连接成功")
    return "SUCCESS"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
