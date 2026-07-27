import os, time, threading, requests, smtplib
from email.mime.text import MIMEText
from email.header import Header
from flask import Flask

app = Flask(__name__)

# 1. Telegram 配置
TELEGRAM_BOT_TOKEN = os.environ.get("BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("CHAT_ID")

# 2. QQ 邮箱配置
QQ_USER = os.environ.get("QQ_USER")  # 发件/收件 QQ 邮箱
QQ_PASS = os.environ.get("QQ_PASS")  # 16 位 QQ 邮箱授权码

# TG 推送函数
def send_tg(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        print("TG推送失败:", e)

# 邮箱推送函数
def send_email(subject, content):
    if not QQ_USER or not QQ_PASS:
        return
    try:
        message = MIMEText(content, 'plain', 'utf-8')
        message['From'] = Header(f"RSI预警助手 <{QQ_USER}>", 'utf-8')
        message['To'] = Header(QQ_USER, 'utf-8')
        message['Subject'] = Header(subject, 'utf-8')

        server = smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=10)
        server.login(QQ_USER, QQ_PASS)
        server.sendmail(QQ_USER, [QQ_USER], message.as_string())
        server.quit()
        print("预警邮件发送成功")
    except Exception as e:
        print("邮件发送失败:", e)

# 双通道统一通知
def notify(title, detail_text):
    send_tg(f"{title}\n{detail_text}")
    clean_text = detail_text.replace('*', '').replace('`', '')
    send_email(title, f"{title}\n\n{clean_text}\n\n发送时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")

def calc_rsi(prices, period=14):
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

def get_rsi_data():
    url = "https://data-api.binance.vision/api/v3/klines"
    res = requests.get(url, params={"symbol": "BTCUSDT", "interval": "1m", "limit": 200}, timeout=10).json()
    
    prices_1m = [float(k[4]) for k in res]
    rsi_1m = calc_rsi(prices_1m)
    
    grouped_10m = {}
    for k in res:
        interval_key = k[0] // 600000
        grouped_10m[interval_key] = float(k[4])
    prices_10m = list(grouped_10m.values())
    rsi_10m = calc_rsi(prices_10m)
    
    latest_price = prices_1m[-1]
    return latest_price, rsi_1m, rsi_10m

# 首页：直接展示当前 BTC 实时价格与 RSI 仪表盘
@app.route('/')
def home():
    try:
        price, rsi_1m, rsi_10m = get_rsi_data()
        now_str = time.strftime('%Y-%m-%d %H:%M:%S')
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>RSI Bot 运行状态</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 20px; background: #f5f5f7; color: #333; }}
                .card {{ background: #fff; padding: 24px; border-radius: 16px; max-width: 380px; margin: 40px auto; box-shadow: 0 4px 20px rgba(0,0,0,0.08); }}
                h2 {{ margin-top: 0; color: #10b981; font-size: 18px; text-align: center; }}
                .item {{ display: flex; justify-content: space-between; margin: 16px 0; font-size: 15px; border-bottom: 1px dashed #eee; padding-bottom: 10px; }}
                .val {{ font-weight: bold; color: #2563eb; }}
                .time {{ color: #888; font-size: 12px; text-align: center; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h2>🟢 RSI Bot 监控运行中</h2>
                <div class="item"><span>交易对</span><span class="val">BTC / USDT (币安)</span></div>
                <div class="item"><span>当前价格</span><span class="val">${price:,.2f}</span></div>
                <div class="item"><span>1m RSI</span><span class="val">{rsi_1m}</span></div>
                <div class="item"><span>10m RSI</span><span class="val">{rsi_10m}</span></div>
                <div class="time">更新时间: {now_str}<br>(刷新网页可看最新数据)</div>
            </div>
        </body>
        </html>
        """
        return html
    except Exception as e:
        return f"RSI Bot 运行中，获取行情数据中: {e}"

def monitor():
    s_1m, s_10m = "NORMAL", "NORMAL"
    HIGH_VAL, LOW_VAL = 85, 15
    
    while True:
        try:
            price, rsi_1m, rsi_10m = get_rsi_data()
            
            if rsi_1m:
                if rsi_1m >= HIGH_VAL and s_1m != "HIGH":
                    notify("🚨 BTC 1m RSI 极度超买！", f"价格: `${price}`\nRSI(1m): *{rsi_1m}* (≥ {HIGH_VAL})")
                    s_1m = "HIGH"
                elif rsi_1m <= LOW_VAL and s_1m != "LOW":
                    notify("🟢 BTC 1m RSI 极度超卖！", f"价格: `${price}`\nRSI(1m): *{rsi_1m}* (≤ {LOW_VAL})")
                    s_1m = "LOW"
                elif LOW_VAL < rsi_1m < HIGH_VAL:
                    s_1m = "NORMAL"

            if rsi_10m:
                if rsi_10m >= HIGH_VAL and s_10m != "HIGH":
                    notify("🚨 BTC 10m RSI 极度超买！", f"价格: `${price}`\nRSI(10m): *{rsi_10m}* (≥ {HIGH_VAL})")
                    s_10m = "HIGH"
                elif rsi_10m <= LOW_VAL and s_10m != "LOW":
                    notify("🟢 BTC 10m RSI 极度超卖！", f"价格: `${price}`\nRSI(10m): *{rsi_10m}* (≤ {LOW_VAL})")
                    s_10m = "LOW"
                elif LOW_VAL < rsi_10m < HIGH_VAL:
                    s_10m = "NORMAL"
        except Exception as e:
            print("监控出错:", e)
        time.sleep(5)  # 5 秒高频检测一次

threading.Thread(target=monitor, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
