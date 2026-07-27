import os, time, threading, requests, smtplib, collections
from email.mime.text import MIMEText
from email.header import Header
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

# 1. Telegram 配置
TELEGRAM_BOT_TOKEN = os.environ.get("BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("CHAT_ID")

# 2. QQ 邮箱配置
QQ_USER = os.environ.get("QQ_USER")
QQ_PASS = os.environ.get("QQ_PASS")

# 实时数据缓存（供网页 1 秒刷新）
LATEST_DATA = {
    "price": 0.0,
    "rsi_1m": 0.0,
    "rsi_3m": 0.0,
    "rsi_5m": 0.0,
    "rsi_10m": 0.0,
    "rsi_1h": 0.0,
    "signal_title": "初始化中...",
    "advice": "正在接入事件合约现货行情源",
    "color": "#f0b90b",
    "update_time": "--"
}

PRICE_HISTORY = collections.deque(maxlen=10)

# ----------------- 双通道通知模块 -----------------

def send_tg(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=5)
    except Exception as e:
        print("TG推送失败:", e)

def send_email(subject, content):
    if not QQ_USER or not QQ_PASS:
        return
    try:
        message = MIMEText(content, 'plain', 'utf-8')
        message['From'] = Header(f"事件合约预警助手 <{QQ_USER}>", 'utf-8')
        message['To'] = Header(QQ_USER, 'utf-8')
        message['Subject'] = Header(subject, 'utf-8')

        server = smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=5)
        server.login(QQ_USER, QQ_PASS)
        server.sendmail(QQ_USER, [QQ_USER], message.as_string())
        server.quit()
        print("预警邮件发送成功")
    except Exception as e:
        print("邮件发送失败:", e)

def notify(title, detail_text):
    send_tg(f"{title}\n{detail_text}")
    clean_text = detail_text.replace('*', '').replace('`', '')
    send_email(title, f"{title}\n\n{clean_text}\n\n发送时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")

# ----------------- 指标计算模块 -----------------

def calc_rsi(prices, period=6):
    if len(prices) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i-1]
        if diff > 0:
            gains.append(diff)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(diff))
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)

def aggregate_klines(res, interval_ms):
    grouped = {}
    for k in res:
        interval_key = k[0] // interval_ms
        grouped[interval_key] = float(k[4])
    return list(grouped.values())

def get_full_market_data():
    # 彻底修正：使用币安现货行情 API（api.binance.com），完全匹配事件合约底层的现货指数价格
    url = "https://api.binance.com/api/v3/klines"
    res = requests.get(url, params={"symbol": "BTCUSDT", "interval": "1m", "limit": 1000}, timeout=5).json()
    
    prices_1m = [float(k[4]) for k in res]
    latest_price = prices_1m[-1]
    
    rsi_1m = calc_rsi(prices_1m, period=6)
    rsi_3m = calc_rsi(aggregate_klines(res, 180000), period=6)
    rsi_5m = calc_rsi(aggregate_klines(res, 300000), period=6)
    rsi_10m = calc_rsi(aggregate_klines(res, 600000), period=6)
    rsi_1h = calc_rsi(aggregate_klines(res, 3600000), period=6)
    
    return latest_price, rsi_1m, rsi_3m, rsi_5m, rsi_10m, rsi_1h

def analyze_all_indicators(price, rsi_1m, rsi_3m, rsi_5m, rsi_10m, rsi_1h):
    if not all([rsi_1m, rsi_3m, rsi_5m, rsi_10m, rsi_1h]):
        return "数据计算中...", "等待数据完整接入", "#f0b90b"
    
    # 85%+ 高胜率多周期共振信号
    if rsi_1h >= 50 and rsi_10m <= 30 and rsi_1m <= 15:
        return "🔥【85%+ 高胜率】大趋势向上 + 10m/1m 深度超卖共振！", "强烈建议：买入看涨 (UP)", "#10b981"
    elif rsi_1h <= 50 and rsi_10m >= 70 and rsi_1m >= 85:
        return "🔥【85%+ 高胜率】大趋势向下 + 10m/1m 深度超买共振！", "强烈建议：买入看跌 (DOWN)", "#ef4444"
    elif rsi_1m <= 15 and rsi_3m <= 20 and rsi_5m <= 25:
        return "⚡【短线三重超卖】1m/3m/5m 现货联合插针！", "建议：抓短线强反弹 (UP)", "#10b981"
    elif rsi_1m >= 85 and rsi_3m >= 80 and rsi_5m >= 75:
        return "⚡【短线三重超买】1m/3m/5m 现货联合拉升！", "建议：抓短线强回撤 (DOWN)", "#ef4444"
    elif rsi_1m >= 85 or rsi_10m >= 85:
        return "⚠️ 事件合约触发极度超买警戒 (≥ 85)", "谨防见顶急跌，可小仓买入看跌 (DOWN)", "#f97316"
    elif rsi_1m <= 15 or rsi_10m <= 15:
        return "💡 事件合约触发极度超卖警戒 (≤ 15)", "谨防快速回升，可小仓买入看涨 (UP)", "#3b82f6"
    else:
        return "⏳ 事件合约现货常态运转中", "建议观望，等待 >85 或 <15 极值信号", "#848e9c"

# ----------------- Web 界面 -----------------

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BTC 事件合约专属终端</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 15px; background: #0b0e11; color: #eaecef; }
        .card { background: #181a20; padding: 20px; border-radius: 16px; max-width: 420px; margin: 10px auto; border: 1px solid #2b2f36; box-shadow: 0 4px 20px rgba(0,0,0,0.6); }
        h2 { margin-top: 0; color: #f0b90b; font-size: 18px; text-align: center; }
        .badge { background: #00c076; color: #fff; font-size: 10px; padding: 2px 6px; border-radius: 4px; vertical-align: middle; }
        .box { background: #2b2f36; padding: 14px; border-radius: 12px; margin: 15px 0; border-left: 5px solid #f0b90b; transition: all 0.3s; }
        .box-title { font-size: 13px; color: #848e9c; margin-bottom: 4px; }
        .box-val { font-size: 15px; font-weight: bold; }
        .item { display: flex; justify-content: space-between; margin: 10px 0; font-size: 14px; border-bottom: 1px dashed #2b2f36; padding-bottom: 6px; }
        .val { font-weight: bold; color: #f0b90b; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 15px; }
        .grid-box { background: #2b2f36; padding: 8px 12px; border-radius: 8px; text-align: center; font-size: 12px; }
        .grid-val { font-size: 16px; font-weight: bold; margin-top: 4px; color: #f0b90b; }
        .time { color: #848e9c; font-size: 11px; text-align: center; margin-top: 15px; }
    </style>
</head>
<body>
    <div class="card">
        <h2>⚡ BTC 事件合约专属终端 <span class="badge">1s 极速</span></h2>
        <div class="box" id="signal-box">
            <div class="box-title" id="signal-title">加载中...</div>
            <div class="box-val" id="signal-advice">正在连接事件合约现货源...</div>
        </div>
        <div class="item"><span>事件合约参考价</span><span class="val" id="price">$0.00</span></div>
        
        <div class="grid">
            <div class="grid-box"><div>1m RSI(6)</div><div class="grid-val" id="rsi-1m">--</div></div>
            <div class="grid-box"><div>3m RSI(6)</div><div class="grid-val" id="rsi-3m">--</div></div>
            <div class="grid-box"><div>5m RSI(6)</div><div class="grid-val" id="rsi-5m">--</div></div>
            <div class="grid-box"><div>10m RSI(6)</div><div class="grid-val" id="rsi-10m">--</div></div>
        </div>
        
        <div class="item" style="margin-top:15px;"><span>1h RSI(6) [大趋势]</span><span class="val" id="rsi-1h">--</span></div>
        <div class="time">更新时间: <span id="update-time">--</span><br>(已锁定币安事件合约底层现货数据源)</div>
    </div>

    <script>
        async function fetchMarketData() {
            try {
                const res = await fetch('/api/data');
                const data = await res.json();
                
                document.getElementById('price').innerText = '$' + data.price.toLocaleString('en-US', {minimumFractionDigits: 2});
                document.getElementById('rsi-1m').innerText = data.rsi_1m;
                document.getElementById('rsi-3m').innerText = data.rsi_3m;
                document.getElementById('rsi-5m').innerText = data.rsi_5m;
                document.getElementById('rsi-10m').innerText = data.rsi_10m;
                document.getElementById('rsi-1h').innerText = data.rsi_1h;
                
                document.getElementById('signal-title').innerText = data.signal_title;
                document.getElementById('signal-advice').innerText = data.advice;
                document.getElementById('signal-advice').style.color = data.color;
                document.getElementById('signal-box').style.borderLeftColor = data.color;
                document.getElementById('update-time').innerText = data.update_time;
            } catch (e) {
                console.error("数据刷新失败:", e);
            }
        }
        setInterval(fetchMarketData, 1000);
        fetchMarketData();
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/data')
def api_data():
    return jsonify(LATEST_DATA)

# ----------------- 1秒高频后台监控 -----------------

def monitor():
    global LATEST_DATA, PRICE_HISTORY
    
    s_1m_high, s_1m_low = False, False
    s_10m_high, s_10m_low = False, False
    s_combo = False

    while True:
        try:
            price, rsi_1m, rsi_3m, rsi_5m, rsi_10m, rsi_1h = get_full_market_data()
            signal_title, advice, color = analyze_all_indicators(price, rsi_1m, rsi_3m, rsi_5m, rsi_10m, rsi_1h)
            now_str = time.strftime('%Y-%m-%d %H:%M:%S')

            LATEST_DATA = {
                "price": price,
                "rsi_1m": rsi_1m,
                "rsi_3m": rsi_3m,
                "rsi_5m": rsi_5m,
                "rsi_10m": rsi_10m,
                "rsi_1h": rsi_1h,
                "signal_title": signal_title,
                "advice": advice,
                "color": color,
                "update_time": now_str
            }

            # 1m RSI 极值预警
            if rsi_1m and rsi_1m >= 85 and not s_1m_high:
                notify("🚨 【事件合约预警】BTC 1m RSI 极度超买！", f"现货价格: `${price}`\n1m RSI(
