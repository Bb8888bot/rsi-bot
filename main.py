import os, time, threading, requests
from flask import Flask

app = Flask(__name__)
TELEGRAM_BOT_TOKEN = os.environ.get("BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("CHAT_ID")

@app.route('/')
def home():
    return "RSI Bot 运行中 (阈值: >85 或 <15)"

def send_tg(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        print("推送失败:", e)

# 纯 Python 计算标准 Wilder RSI
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
    url = "https://api.binance.com/api/v3/klines"
    res = requests.get(url, params={"symbol": "BTCUSDT", "interval": "1m", "limit": 200}, timeout=10).json()
    
    prices_1m = [float(k[4]) for k in res]
    rsi_1m = calc_rsi(prices_1m)
    
    # 10分钟 K 线聚合
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
                    send_tg(f"🚨 *BTC 1m RSI 极度超买！*\n价格: `${price}`\nRSI(1m): *{rsi_1m}* (≥ {HIGH_VAL})")
                    s_1m = "HIGH"
                elif rsi_1m <= LOW_VAL and s_1m != "LOW":
                    send_tg(f"🟢 *BTC 1m RSI 极度超卖！*\n价格: `${price}`\nRSI(1m): *{rsi_1m}* (≤ {LOW_VAL})")
                    s_1m = "LOW"
                elif LOW_VAL < rsi_1m < HIGH_VAL:
                    s_1m = "NORMAL"

            if rsi_10m:
                if rsi_10m >= HIGH_VAL and s_10m != "HIGH":
                    send_tg(f"🚨 *BTC 10m RSI 极度超买！*\n价格: `${price}`\nRSI(10m): *{rsi_10m}* (≥ {HIGH_VAL})")
                    s_10m = "HIGH"
                elif rsi_10m <= LOW_VAL and s_10m != "LOW":
                    send_tg(f"🟢 *BTC 10m RSI 极度超卖！*\n价格: `${price}`\nRSI(10m): *{rsi_10m}* (≤ {LOW_VAL})")
                    s_10m = "LOW"
                elif LOW_VAL < rsi_10m < HIGH_VAL:
                    s_10m = "NORMAL"
        except Exception as e:
            print("监控出错:", e)
        time.sleep(30)

threading.Thread(target=monitor, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
