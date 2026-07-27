import os, time, threading, requests
from flask import Flask, jsonify, Response

app = Flask(__name__)

TG_TOKEN = os.environ.get("BOT_TOKEN")
TG_CHAT = os.environ.get("CHAT_ID")
PP_TOKEN = os.environ.get("PUSHPLUS_TOKEN")

DATA = {
    "price": 0.0, "rsi_1m": 50.0, "rsi_3m": 50.0, "rsi_5m": 50.0, "rsi_10m": 50.0, "rsi_1h": 50.0,
    "title": "初始化中", "advice": "正在同步数据源", "color": "#f0b90b", "time": "--"
}

def get_beijing_time():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 28800))

def send_tg(msg):
    if TG_TOKEN and TG_CHAT:
        try:
            r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": TG_CHAT, "text": msg}, timeout=5)
            return True, r.text
        except Exception as e:
            return False, str(e)
    return False, "TG 未配置"

def send_wx(title, content):
    if not PP_TOKEN:
        return False, "PushPlus Token 未配置"
    try:
        url = "http://www.pushplus.plus/send"
        data = {
            "token": PP_TOKEN.strip(),
            "title": title,
            "content": content.replace("\n", "<br>"),
            "template": "html"
        }
        r = requests.post(url, json=data, timeout=5)
        res = r.json()
        if res.get("code") == 200:
            return True, "发送成功"
        return False, res.get("msg", "发送失败")
    except Exception as e:
        return False, str(e)

def notify(title, text):
    send_tg(f"{title}\n{text}")
    send_wx(title, f"{text}\n\n时间: {get_beijing_time()}")

HTML_PAGE = """<!DOCTYPE html>
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
<div class="time">更新时间 (北京时间): <br><span id="ut" style="color:#f0b90b;font-weight:bold">--</span></div>
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
    return Response(HTML_PAGE, mimetype="text/html")

@app.route('/api/data')
def api_data():
    return jsonify(DATA)

@app.route('/test')
def test_push():
    bj_time = get_beijing_time()
    t_msg = f"测试事件合约消息通知\n测试时间: {bj_time}"
    tg_ok, tg_info = send_tg(f"🧪【测试】\n{t_msg}")
    wx_ok, wx_info = send_wx("🧪【测试预警】微信通道连通性测试", t_msg)
    
    tg_res = "✅ 成功" if tg_ok else f"❌ 失败 ({tg_info})"
    wx_res = "✅ 成功" if wx_ok else f"❌ 失败 (原因: {wx_info})"
    
    html = f"<html><body style='padding:20px;background:#181a20;color:#fff;'><h2>🧪 通道实时诊断结果</h2><p><b>1. Telegram:</b> {tg_res}</p><p><b>2. 微信弹窗:</b> {wx_res}</p><hr><p>时间: {bj_time}</p></body></html>"
    return Response(html, mimetype="text/html")

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

def agg_klines(res, ms):
    g = {}
    for k in res:
        g[k[0] // ms] = float(k[4])
    return list(g.values())

def fetch_data():
    urls = [
        "https://data-api.binance.vision/api/v3/klines",
        "https://api.binance.com/api/v3/klines",
        "https://api1.binance.com/api/v3/klines"
    ]
    headers = {"User-Agent": "Mozilla/5.0"}
    res = None
    for u in urls:
        try:
            r = requests.get(u, params={"symbol": "BTCUSDT", "interval": "1m", "limit": 1000}, headers=headers, timeout=3)
            if r.status_code == 200:
                res = r.json()
                break
        except:
            continue
    if not res:
        raise Exception("超时")

    p1m = [float(k[4]) for k in res]
    p = p1m[-1]
    r1 = calc_rsi_wilder(p1m, 6)
    r3 = calc_rsi_wilder(agg_klines(res, 180000), 6)
    r5 = calc_rsi_wilder(agg_klines(res, 300000), 6)
    r10 = calc_rsi_wilder(agg_klines(res, 600000), 6)
    r1h = calc_rsi_wilder(agg_klines(res, 3600000), 6)
    return p, r1, r3, r5, r10, r1h

def analyze(p, r1, r3, r5, r10, r1h):
    if r1h >= 50 and r10 <= 30 and r1 <= 15:
        return "【85%+高胜率】趋势向上+超卖共振", "强烈建议：买入看涨 (UP)", "#10b981"
    if r1h <= 50 and r10 >= 70 and r1 >= 85:
        return "【85%+高胜率】趋势向下+超买共振", "强烈建议：买入看跌 (DOWN)", "#ef4444"
    if r1 <= 15 and r3 <= 20 and r5 <= 25:
        return "【短线三重超卖】1m/3m/5m插针", "建议：抓短线反弹 (UP)", "#10b981"
    if r1 >= 85 and r3 >= 80 and r5 >= 75:
        return "【短线三重超买】1m/3m/5m拉升", "建议：抓短线回撤 (DOWN)", "#ef4444"
    if r1 >= 85 or r10 >= 85:
        return "触发极度超买警戒 (>=85)", "谨防见顶急跌，可小仓看跌 (DOWN)", "#f97316"
    if r1 <= 15 or r10 <= 15:
        return "触发极度超卖警戒 (<=15)", "谨防快速回升，可小仓看涨 (UP)", "#3b82f6"
    return "事件合约常态运转中", "建议观望，等待>85或<15极值信号", "#848e9c"

def monitor():
    global DATA
    s1_h = s1_l = s10_h = s10_l = s_combo = False
    while True:
        try:
            p, r1, r3, r5, r10, r1h = fetch_data()
            title, adv, color = analyze(p, r1, r3, r5, r10, r1h)
            bj_time = get_beijing_time()
            DATA = {
                "price": p, "rsi_1m": r1, "rsi_3m": r3, "rsi_5m": r5,
                "rsi_10m": r10, "rsi_1h": r1h, "title": title,
                "advice": adv, "color": color, "time": bj_time
            }
            if r1 >= 85 and not s1_h:
                notify("🚨【预警】BTC 1m RSI 极度超买！", f"参考价: ${p}\n1m RSI(6): {r1}")
                s1_h = True
            elif r1 <= 15 and not s1_l:
                notify("🟢【预警】BTC 1m RSI 极度超卖！", f"参考价: ${p}\n1m RSI(6): {r1}")
                s1_l = True
            elif 25 < r1 < 75:
                s1_h = s1_l = False

            if r10 >= 85 and not s10_h:
                notify("🚨【重磅】BTC 10m RSI 极度超买！", f"参考价: ${p}\n10m RSI(6): {r10}")
                s10_h = True
            elif r10 <= 15 and not s10_l:
                notify("🟢【重磅】BTC 10m RSI 极度超卖！", f"参考价: ${p}\n10m RSI(6): {r10}")
                s10_l = True
            elif 25 < r10 < 75:
                s10_h = s10_l = False

            if r1h >= 50 and r10 <= 30 and r1 <= 15 and not s_combo:
                notify("🔥【85%+高胜率】买入看涨 (UP)！", f"参考价: ${p}\n1h:{r1h} | 10m:{r10} | 1m:{r1}")
                s_combo = True
            elif r1h <= 50 and r10 >= 70 and r1 >= 85 and not s_combo:
                notify("🔥【85%+高胜率】买入看跌 (DOWN)！", f"参考价: ${p}\n1h:{r1h} | 10m:{r10} | 1m:{r1}")
                s_combo = True
            elif 20 < r1 < 80 and 35 < r10 < 65:
                s_combo = False

        except Exception as e:
            print("Monitor error:", e)
        time.sleep(1)

threading.Thread(target=monitor, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
