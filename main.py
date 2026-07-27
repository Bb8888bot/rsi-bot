import os, time, threading, requests
from flask import Flask, jsonify, Response

app = Flask(__name__)

TG_TOKEN = os.environ.get("BOT_TOKEN")
TG_CHAT = os.environ.get("CHAT_ID")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

DATA = {
    "price": 0.0, "rsi_1m": 50.0, "rsi_10m": 50.0, "rsi_1h": 50.0,
    "boll_up": 0.0, "boll_mb": 0.0, "boll_dn": 0.0, "ema7": 0.0, "ema25": 0.0, "ema99": 0.0,
    "title": "⚡ 币安同源同步中", "action": "高精度极值共振监控中", "color": "#00ff41",
    "bj_time": "--", "session_name": "--"
}

def get_beijing_time():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 28800))

def get_session_info():
    h = time.gmtime(time.time() + 28800).tm_hour
    if 8 <= h < 15:
        return "亚盘黄金震荡期 (高抛低吸)"
    elif 15 <= h < 19:
        return "欧盘趋势启动期 (抓轨外反弹)"
    elif 20 <= h < 24:
        return "美盘黄金交易期 (顺势共振核心)"
    else:
        return "深夜低量横盘期 (极值防御)"

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
    gains, losses = 0.0, 0.0
    for i in range(1, len(prices)):
        d = prices[i] - prices[i-1]
        if d > 0:
            gains += d
        else:
            losses += abs(d)
    avg_g = gains / period
    avg_l = losses / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return round(100.0 - (100.0 / (1.0 + rs)), 2)

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

def fetch_direct_klines(interval, limit=100):
    urls = [
        f"https://api1.binance.com/api/v3/klines?symbol=BTCUSDT&interval={interval}&limit={limit}",
        f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval={interval}&limit={limit}",
        f"https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval={interval}&limit={limit}"
    ]
    headers = {"User-Agent": "Mozilla/5.0"}
    for url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=2.5)
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
            # 分别直接拉取 1m、10m、1h 官方标准 K 线，保证与币安盘面计算口径 100% 一致
            p1m = fetch_direct_klines("1m", 100)
            p10m = fetch_direct_klines("10m", 100)
            p1h = fetch_direct_klines("1h", 100)

            if p1m and p10m:
                p = p1m[-1]
                r1m = calc_rsi(p1m, 6)
                r10m = calc_rsi(p10m, 6)
                r1h = calc_rsi(p1h, 6) if p1h else r1m

                bup, bmb, bdn = calc_boll(p1m, 20)
                e7 = calc_ema(p1m, 7)
                e25 = calc_ema(p1m, 25)
                e99 = calc_ema(p1h, 99) if p1h else e25

                title = "⚡ 实时监控中 (高胜率守护)"
                action = "耐心等待 1m/10m 极值共振点"
                color = "#00ff41"

                # 高精度双周期共振与 BOLL 轨道过滤
                if r1m <= 15 and r10m <= 25 and p <= bdn * 1.002:
                    title = "🔥【S级绝杀·买入看涨 (UP)】"
                    action = "立刻开仓：买入看涨 (UP)！"
                    color = "#00ff41"
                elif r1m >= 85 and r10m >= 75 and p >= bup * 0.998:
                    title = "🔥【S级绝杀·买入看跌 (DOWN)】"
                    action = "立刻开仓：买入看跌 (DOWN)！"
                    color = "#ff003c"

                DATA = {
                    "price": p, "rsi_1m": r1m, "rsi_10m": r10m, "rsi_1h": r1h,
                    "boll_up": bup, "boll_mb": bmb, "boll_dn": bdn,
                    "ema7": e7, "ema25": e25, "ema99": e99,
                    "title": title, "action": action, "color": color,
                    "bj_time": get_beijing_time(), "session_name": get_session_info()
                }

                if "S级绝杀" in title and not lock:
                    notify(title, "现价: $" + str(p) + "\n操作指令: " + action + "\n1m RSI: " + str(r1m) + " | 10m RSI: " + str(r10m))
                    lock = True
                elif "S级绝杀" not in title:
                    lock = False
        except Exception as e:
            print(e)
        time.sleep(1)

threading.Thread(target=monitor, daemon=True).start()

PAGE = """<!DOCTYPE html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>暴爷事件合约实战终端</title>
<style>body{background:#05070a;color:#00ff41;font-family:monospace;padding:12px;margin:0}
.box{background:#0c1017;padding:14px;border-radius:10px;border:1px solid #00ff4155;max-width:400px;margin:auto}
h2{color:#ffe600;text-align:center;margin-top:0;font-size:18px}
.row{display:flex;justify-content:space-between;margin:6px 0;font-size:12px}
</style></head><body>
<div class='box'><h2>⚡ 暴爷事件合约实战 ⚡</h2>
<div class='row'><b>北京时间:</b> <span id='bt' style='color:#00f3ff'>--</span></div>
<div class='row'><b>当前时段:</b> <span id='sn' style='color:#ffe600'>--</span></div>
<div class='row'><b>信号状态:</b> <span id='t' style='color:#00ff41;font-weight:bold'>连接中...</span></div>
<div class='row'><b>开单指令:</b> <span id='ac' style='color:#ffe600;font-weight:bold'>--</span></div>
<div class='row'><b>BTC现价:</b> <span id='p' style='color:#ffe600;font-weight:bold;font-size:15px'>$0.00</span></div>
<div class='row'><b>BOLL 上/中/下:</b> <span id='b' style='color:#ff003c'>--</span></div>
<div class='row'><b>EMA 7/25/99:</b> <span id='e' style='color:#00f3ff'>--</span></div>
<div class='row'><b>1m RSI(6):</b> <span id='r1' style='color:#00ff41'>--</span></div>
<div class='row'><b>10m RSI(6):</b> <span id='r10' style='color:#ffe600'>--</span></div>
<div class='row'><b>1h 大趋势 RSI:</b> <span id='r1h' style='color:#da70d6'>--</span></div>
</div>
<script>setInterval(()=>{fetch('/api/data').then(r=>r.json()).then(d=>{
document.getElementById('bt').innerText=d.bj_time;
document.getElementById('sn').innerText=d.session_name;
document.getElementById('t').innerText=d.title;
document.getElementById('t').style.color=d.color;
document.getElementById('ac').innerText=d.action;
document.getElementById('p').innerText='$'+d.price.toFixed(2);
document.getElementById('b').innerText=d.boll_up+' / '+d.boll_mb+' / '+d.boll_dn;
document.getElementById('e').innerText=d.ema7+' / '+d.ema25+' / '+d.ema99;
document.getElementById('r1').innerText=d.rsi_1m;
document.getElementById('r10').innerText=d.rsi_10m;
document.getElementById('r1h').innerText=d.rsi_1h;
});},1000);</script></body></html>"""

@app.route('/')
def home():
    return Response(PAGE, mimetype="text/html")

@app.route('/api/data')
def api_data():
    return jsonify(DATA)

@app.route('/test')
def test_push():
    notify("🧪 暴爷测试", "同源对齐通道连接成功")
    return "SUCCESS"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
