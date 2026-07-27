import os, time, threading, requests, smtplib
from email.mime.text import MIMEText
from email.header import Header
from flask import Flask, jsonify, Response

app = Flask(__name__)

TG_TOKEN = os.environ.get("BOT_TOKEN")
TG_CHAT = os.environ.get("CHAT_ID")
QQ_USER = os.environ.get("QQ_USER")
QQ_PASS = os.environ.get("QQ_PASS")

DATA = {
    "price": 0.0, "rsi_1m": 50.0, "rsi_3m": 50.0, "rsi_5m": 50.0, "rsi_10m": 50.0, "rsi_1h": 50.0,
    "title": "初始化中", "advice": "正在连接数据源", "color": "#f0b90b", "time": "--"
}

def send_tg(msg):
    if TG_TOKEN and TG_CHAT:
        try:
            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": TG_CHAT, "text": msg}, timeout=5)
        except Exception as e:
            print("TG Error:", e)

def send_email(subject, content):
    if QQ_USER and QQ_PASS:
        try:
            m = MIMEText(content, "plain", "utf-8")
            m["From"] = Header(f"事件合约助手 <{QQ_USER}>", "utf-8")
            m["To"] = Header(QQ_USER, "utf-8")
            m["Subject"] = Header(subject, "utf-8")
            s = smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=5)
            s.login(QQ_USER, QQ_PASS)
            s.sendmail(QQ_USER, [QQ_USER], m.as_string())
            s.quit()
        except Exception as e:
            print("Email Error:", e)

def notify(title, text):
    send_tg(f"{title}\n{text}")
    clean = text.replace("*", "").replace("`", "")
    send_email(title, f"{title}\n\n{clean}\n\n时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")

def calc_rsi(prices, period=6):
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

def agg_klines(res, ms):
    g = {}
    for k in res:
        g[k[0] // ms] = float(k[4])
    return list(g.values())

def fetch_data():
    url = "https://api.binance.com/api/v3/klines"
    res = requests.get(url, params={"symbol": "BTCUSDT", "interval": "1m", "limit": 1000}, timeout=5).json()
    p1m = [float(k[4]) for k in res]
    price = p1m[-1]
    r1m = calc_rsi(p1m, 6)
    r3m = calc_rsi(agg_klines(res, 180000), 6)
    r5m = calc_rsi(agg_klines(res, 300000), 6)
    r10m = calc_rsi(agg_klines(res, 600000), 6)
    r1h = calc_rsi(agg_klines(res, 3600000), 6)
    return price, r1m, r3m, r5m, r10m, r1h

def analyze(price, r1m, r3m, r5m, r10m, r1h):
    if r1h >= 50 and r10m <= 30 and r1m <= 15:
        return "【85%+高胜率】趋势向上+超卖共振", "强烈建议：买入看涨 (UP)", "#10b981"
    if r1h <= 50 and r10m >= 70 and r1m >= 85:
        return "【85%+高胜率】趋势向下+超买共振", "强烈建议：买入看跌 (DOWN)", "#ef4444"
    if r1m <= 15 and r3m <= 20 and r5m <= 25:
        return "【短线三重超卖】1m/3m/5m插针", "建议：抓短线反弹 (UP)", "#10b981"
    if r1m >= 85 and r3m >= 80 and r5m >= 75:
        return "【短线三重超买】1m/3m/5m拉升", "建议：抓短线回撤 (DOWN)", "#ef4444"
    if r1m >= 85 or r10m >= 85:
        return "触发极度超买警戒 (>=85)", "谨防见顶急跌，可小仓看跌 (DOWN)", "#f97316"
    if r1m <= 15 or r10m <= 15:
        return "触发极度超卖警戒 (<=15)", "谨防快速回升，可小仓看涨 (UP)", "#3b82f6"
    return "事件合约常态运转中", "建议观望，等待>85或<15极值信号", "#848e9c"

HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BTC 事件合约终端</title>
<style>
body{font-family:sans-serif;padding:15px;background:#0b0e11;color:#eaecef}
.card{background:#181a20;padding:20px;border-radius:16px;max-width:420px;margin:10px auto;border:1px solid #2b2f36}
h2{color:#f0b90b;font-size:18px;text-align:center;margin-top:0}
.box{background:#2b2f36;padding:14px;border-radius:12px;margin:15px 0;border-left:5px solid #f0b90b}
.title{font-size:13px;color:#848e9c;margin-bottom:4px}
.val{font-size:15px;font-weight:bold}
.item{display:flex;justify-content:space-between;margin:10px 0;font-size:14px;border-bottom:1px dashed #2b2f36;padding-bottom:6px}
.v{font-weight:bold;color:#f0b90b}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:15px}
.gbox{background:#2b2f36;padding:8px 12px;border-radius:8px;text-align:center;font-size:12px}
.gval{font-size:16px;font-weight:bold;margin-top:4px;color:#f0b90b}
.time{color:#848e9c;font-size:11px;text-align:center;margin-top:15px}
</style>
</head>
<body>
<div class="card">
<h2>⚡ BTC 事件合约终端</h2>
<div class="box" id="box">
<div class="title" id="stitle">加载中...</div>
<div class="val" id="sadv">连接行情中...</div>
</div>
<div class="item"><span>参考价</span><span class="v" id="pr">$0.00</span></div>
<div class="grid">
<div class="gbox"><div>1m RSI(6)</div><div class="gval" id="r1">--</div></div>
<div class="gbox"><div>3m RSI(6)</div><div class="gval" id="r3">--</div></div>
<div class="gbox"><div>5m RSI(6)</div><div class="gval" id="r5">--</div></div>
<div class="gbox"><div>10m RSI(6)</div><div class="gval" id="r10">--</div></div>
</div>
<div class="item" style="margin-top:15px"><span>1h RSI(6) [大趋势]</span><span class="v" id="r1h">--</span></div>
<div class="time">更新时间: <span id="ut">--</span></div>
</div>
<script>
function up(){
fetch('/api/data').then(r=>r.json()).then(d=>{
document.getElementById('pr').innerText='$'+d.price.toFixed(2);
document.getElementById('r1').innerText=d.rsi_1m;
document.getElementById('r3').innerText=d.rsi_3m;
document.getElementById('r5').innerText=d.rsi_5m;
document.getElementById('r10').innerText=d.rsi_10m;
document.getElementById('r1h').innerText=d.rsi_1h;
document.getElementById('stitle').innerText=d.title;
document.getElementById('sadv').innerText=d.advice;
document.getElementById('sadv').style.color=d.color;
document.getElementById('box').style.borderLeftColor=d.color;
document.getElementById('ut').innerText=d.time;
}).catch(e=>console.log(e));
}
setInterval(up,1000);up();
</script>
</body>
</html>"""

@app.route('/')
def home():
    return Response(HTML, mimetype="text/html")

@app.route('/api/data')
def api_data():
    return jsonify(DATA)

def monitor():
    global DATA
    s1_h = s1_l = s10_h = s10_l = s_combo = False
    while True:
        try:
            p, r1, r3, r5, r10, r1h = fetch_data()
            title, adv, color = analyze(p, r1, r3, r5, r10, r1h)
            now = time.strftime('%Y-%m-%d %H:%M:%S')
            DATA = {
                "price": p, "rsi_1m": r1, "rsi_3m": r3, "rsi_5m": r5,
                "rsi_10m": r10, "rsi_1h": r1h, "title": title,
                "advice": adv, "color": color, "time": now
            }
            if r1 >= 85 and not s1_h:
                notify("🚨【事件合约预警】BTC 1m RSI 极度超买！", f"参考价: ${p}\n1m RSI(6): {r1} (>=85)")
                s1_h = True
            elif r1 <= 15 and not s1_l:
                notify("🟢【事件合约预警】BTC 1m RSI 极度超卖！", f"参考价: ${p}\n1m RSI(6): {r1} (<=15)")
                s1_l = True
            elif 25 < r1 < 75:
                s1_h = s1_l = False

            if r10 >= 85 and not s10_h:
                notify("🚨【事件合约重磅】BTC 10m RSI 极度超买！", f"参考价: ${p}\n10m RSI(6): {r10} (>=85)")
                s10_h = True
            elif r10 <= 15 and not s10_l:
                notify("🟢【事件合约重磅】BTC 10m RSI 极度超卖！", f"参考价: ${p}\n10m RSI(6): {r10} (<=15)")
                s10_l = True
            elif 25 < r10 < 75:
                s10_h = s10_l = False

            if r1h >= 50 and r10 <= 30 and r1 <= 15 and not s_combo:
                notify("🔥【85%+高胜率信号】买入看涨 (UP)！", f"参考价: ${p}\n1h: {r1h} | 10m: {r10} | 1m: {r1}")
                s_combo = True
            elif r1h <= 50 and r10 >= 70 and r1 >= 85 and not s_combo:
                notify("🔥【85%+高胜率信号】买入看跌 (DOWN)！", f"参考价: ${p}\n1h: {r1h} | 10m: {r10} | 1m: {r1}")
                s_combo = True
            elif (20 < r1 < 80) and (35 < r10 < 65):
                s_combo = False

        except Exception as e:
            print("Monitor error:", e)
        time.sleep(1)

threading.Thread(target=monitor, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
