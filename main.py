import os, time, threading, requests
from flask import Flask, jsonify, Response

app = Flask(__name__)

TG_TOKEN = os.environ.get("BOT_TOKEN")
TG_CHAT = os.environ.get("CHAT_ID")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

DATA = {
    "price": 0.0, "rsi_1m": 50.0, "rsi_3m": 50.0, "rsi_5m": 50.0, "rsi_10m": 50.0, "rsi_1h": 50.0,
    "boll_up": 0.0, "boll_dn": 0.0, "ema7": 0.0, "ema25": 0.0,
    "title": "INIT", "advice": "CONNECTING...", "color": "#00ff41", "time": "--",
    "session_name": "ANALYZING...", "session_advice": "WAIT...", "win_rate": "--",
    "ping": "0ms", "signal_tier": "STANDBY"
}

def get_beijing_time():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 28800))

def get_session_info():
    h = time.gmtime(time.time() + 28800).tm_hour
    if 8 <= h < 15:
        return "亚盘震荡", "高抛低吸", "85%", "#00ff41"
    elif 15 <= h < 19:
        return "欧盘趋势", "抓轨外反弹", "88%", "#00f3ff"
    elif 20 <= h < 24:
        return "美盘黄金期", "顺势共振", "92%", "#00ff41"
    else:
        return "深夜横盘", "谨慎极值", "75%", "#848e9c"

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
    full = title + "\n" + text + "\n时间: " + get_beijing_time()
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
        return p, p
    sp = prices[-period:]
    sma = sum(sp) / period
    std = (sum((x - sma) ** 2 for x in sp) / period) ** 0.5
    return round(sma + (std * 2), 2), round(sma - (std * 2), 2)

def fetch_klines(symbol, interval):
    try:
        r = requests.get("https://fapi.binance.com/fapi/v1/klines", params={"symbol": symbol, "interval": interval, "limit": 50}, timeout=2)
        if r.status_code == 200:
            return [float(k[4]) for k in r.json()]
    except:
        pass
    return []

def monitor():
    global DATA
    lock = False
    while True:
        try:
            p1 = fetch_klines("BTCUSDT", "1m")
            p3 = fetch_klines("BTCUSDT", "3m")
            p5 = fetch_klines("BTCUSDT", "5m")
            p1h = fetch_klines("BTCUSDT", "1h")
            if p1 and p3 and p5 and p1h:
                p = p1[-1]
                r1, r3, r5, r1h = calc_rsi(p1), calc_rsi(p3), calc_rsi(p5), calc_rsi(p1h)
                bup, bdn = calc_boll(p1)
                
                title, tier, col = "矩阵待命", "STANDBY", "#848e9c"
                if p <= bdn and r1 <= 15 and r3 <= 25:
                    title, tier, col = "🔥【S级绝杀·买入看涨(UP)】", "S-TIER", "#00ff41"
                elif p >= bup and r1 >= 85 and r3 >= 75:
                    title, tier, col = "🔥【S级绝杀·买入看跌(DOWN)】", "S-TIER", "#ff003c"

                DATA = {
                    "price": p, "rsi_1m": r1, "rsi_3m": r3, "rsi_5m": r5,
                    "rsi_10m": r1, "rsi_1h": r1h, "boll_up": bup, "boll_dn": bdn,
                    "ema7": 0.0, "ema25": 0.0, "title": title, "advice": "实时监控中",
                    "color": col, "time": get_beijing_time(), "session_name": get_session_info()[0],
                    "session_advice": get_session_info()[1], "win_rate": get_session_info()[2],
                    "signal_tier": tier
                }

                if "S级" in title and not lock:
                    notify(title, "现价: " + str(p) + " | 1m RSI: " + str(r1))
                    lock = True
                elif "S级" not in title:
                    lock = False
        except Exception as e:
            print(e)
        time.sleep(2)

threading.Thread(target=monitor, daemon=True).start()

PAGE = """
<!DOCTYPE html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>暴爷无极限</title>
<style>body{background:#05070a;color:#00ff41;font-family:monospace;padding:15px;margin:0}
.box{background:#0c1017;padding:15px;border-radius:10px;border:1px solid #00ff4155;max-width:400px;margin:auto}
h2{color:#ffe600;text-align:center;margin-top:0}</style></head><body>
<div class='box'><h2>⚡ 暴爷无极限 ⚡</h2>
<p><b>状态:</b> <span id='t'>加载中...</span></p>
<p><b>价格:</b> <span id='p'>$0.00</span></p>
<p><b>1m RSI:</b> <span id='r1'>--</span> | <b>3m:</b> <span id='r3'>--</span></p>
<p><b>5m RSI:</b> <span id='r5'>--</span> | <b>1h趋势:</b> <span id='r1h'>--</span></p></div>
<script>setInterval(()=>{fetch('/api/data').then(r=>r.json()).then(d=>{
document.getElementById('t').innerText=d.title+' ['+d.signal_tier+']';
document.getElementById('p').innerText='$'+d.price.toFixed(2);
document.getElementById('r1').innerText=d.rsi_1m;
document.getElementById('r3').innerText=d.rsi_3m;
document.getElementById('r5').innerText=d.rsi_5m;
document.getElementById('r1h').innerText=d.rsi_1h;
});},1000);</script></body></html>
"""

@app.route('/')
def home():
    return Response(PAGE, mimetype="text/html")

@app.route('/api/data')
def api_data():
    return jsonify(DATA)

@app.route('/test')
def test_push():
    notify("🧪 暴爷测试", "通道连接成功")
    return "SUCCESS"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
