import os, time, threading, requests
from flask import Flask
import pandas as pd

app = Flask(__name__)
TELEGRAM_BOT_TOKEN = os.environ.get("BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("CHAT_ID")

@app.route('/')
def home():
    return "RSI Bot 运行中"

def send_tg(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        print("推送失败:", e)

def get_rsi(symbol="BTCUSDT", interval="1m"):
    url = "https://api.binance.com/api/v3/klines"
    res = requests.get(url, params={"symbol": symbol, "interval": "1m", "limit": 200}, timeout=10).json()
    df = pd.DataFrame(res, columns=['time','open','high','low','close','vol','ct','qav','nt','tb','tq','ig'])
    df['close'] = df['close'].astype(float)
    
    if interval == "10m":
        df['time'] = pd.to_datetime(df['time'], unit='ms')
        df = df.resample('10min', on='time').agg({'close': 'last'}).dropna()

    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs = avg_gain / avg_loss
    df['rsi'] = 100 - (100 / (1 + rs))
    return df['close'].iloc[-1], round(df['rsi'].iloc[-1], 2)

def monitor():
    s_1m, s_10m = "NORMAL", "NORMAL"
    while True:
        try:
            price, rsi_1m = get_rsi(interval="1m")
            if rsi_1m >= 70 and s_1m != "HIGH":
                send_tg(f"🚨 *BTC 1m RSI 超买预警！*\n价格: `${price}`\nRSI(1m): *{rsi_1m}*")
                s_1m = "HIGH"
            elif rsi_1m <= 30 and s_1m != "LOW":
                send_tg(f"🟢 *BTC 1m RSI 超卖预警！*\n价格: `${price}`\nRSI(1m): *{rsi_1m}*")
                s_1m = "LOW"
            elif 30 < rsi_1m < 70:
                s_1m = "NORMAL"

            _, rsi_10m = get_rsi(interval="10m")
            if rsi_10m >= 70 and s_10m != "HIGH":
                send_tg(f"🚨 *BTC 10m RSI 超买预警！*\n价格: `${price}`\nRSI(10m): *{rsi_10m}*")
                s_10m = "HIGH"
            elif rsi_10m <= 30 and s_10m != "LOW":
                send_tg(f"🟢 *BTC 10m RSI 超卖预警！*\n价格: `${price}`\nRSI(10m): *{rsi_10m}*")
                s_10m = "LOW"
            elif 30 < rsi_10m < 70:
                s_10m = "NORMAL"
        except Exception as e:
            print("监控出错:", e)
        time.sleep(30)

threading.Thread(target=monitor, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
