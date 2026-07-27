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

@app.route('/')
def home():
    return "RSI Bot 运行中 (5秒高频监控 | TG + QQ邮箱双推送)"

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

        # 连接 QQ 邮箱 SSL 加密端口 465
        server = smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=10)
        server.login(QQ_USER, QQ_PASS)
        server.sendmail(QQ_USER, [QQ_USER], message.as_string())
        server.quit()
        print("预警邮件发送成功")
    except Exception as e:
        print("邮件发送失败:", e)

# 双通道统一通知
def notify(title, detail_text):
    # 1. 发送 Telegram (需要 VPN)
    send_tg(f"{title}\n{detail_text}")
    # 2. 发送 QQ 邮箱 (国内直连最稳)
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
