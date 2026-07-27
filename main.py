import os
import time
import json
import requests
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta
import websocket

# --- 环境变量配置 ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
SYMBOL = "btcusdt"
RSI_PERIOD = 6  # 匹配事件合约交易界面常用的 RSI(6) 指标

# 历史收盘价数据池（用于计算 RSI）
klines_1m = []   # 1m K线收盘价
klines_10m = []  # 10m K线收盘价（由 1m 自动聚合）
klines_1h = []   # 1h K线收盘价

temp_1m_buffer = []  # 10m 聚合缓存

# 报警冷却字典（防止同周期极端行情秒级重复轰炸）
last_alert_times = {
    "1m": 0,
    "10m": 0,
    "1h": 0
}
ALERT_COOLDOWN = 60  # 同周期 60 秒内只触发一次推送

def get_beijing_time():
    bj_tz = timezone(timedelta(hours=8))
    return datetime.now(bj_tz).strftime("%Y-%m-%d %H:%M:%S")

def send_telegram(msg):
    bj_time = get_beijing_time()
    print(f"[{bj_time}] 📢 触发预警:\n{msg}")
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Telegram 推送失败: {e}")

def calculate_rsi(prices, period=RSI_PERIOD):
    if len(prices) < period + 1:
        return 50.0
    deltas = [prices[i] - prices[i-1] for i in range(len(prices)-period, len(prices))]
    gains = [d for d in deltas if d > 0]
    losses = [-d for d in deltas if d < 0]
    avg_gain = sum(gains) / period if gains else 0
    avg_loss = sum(losses) / period if losses else 0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def fetch_initial_klines():
    """启动时从多个备用 API 节点预加载历史数据，确保上线即可精准计算 RSI"""
    global klines_1m, klines_10m, klines_1h
    api_hosts = [
        "https://api.binance.com",
        "https://api1.binance.com",
        "https://api3.binance.com",
        "https://data-api.binance.vision"
    ]
    
    for host in api_hosts:
        try:
            # 1. 获取 1m 历史 K线
            resp_1m = requests.get(f"{host}/api/v3/klines?symbol=BTCUSDT&interval=1m&limit=120", timeout=5)
            if resp_1m.status_code == 200:
                data_1m = resp_1m.json()
                klines_1m = [float(x[4]) for x in data_1m[:-1]]
                
                # 聚合 10m 历史
                klines_10m = klines_1m[9::10]
                
                # 2. 获取 1h 历史 K线
                resp_1h = requests.get(f"{host}/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=60", timeout=5)
                if resp_1h.status_code == 200:
                    data_1h = resp_1h.json()
                    klines_1h = [float(x[4]) for x in data_1h[:-1]]
                    
                print(f"[{get_beijing_time()}] ✅ 成功从节点 {host} 预加载历史 K 线！")
                return
        except Exception as e:
            print(f"从节点 {host} 拉取失败，尝试下一个...")
            continue

def check_and_notify(timeframe, current_price, rsi_value):
    now_ts = time.time()
    if now_ts - last_alert_times[timeframe] < ALERT_COOLDOWN:
        return

    bj_time = get_beijing_time()

    if rsi_value >= 85:
        last_alert_times[timeframe] = now_ts
        msg = (
            f"🚨 **BTCUSDT 事件合约【{timeframe} 周期】超买预警**\n"
            f"⏰ **北京时间**: `{bj_time}`\n"
            f"💰 **当前价格**: `{current_price:.2f}`\n"
            f"📊 **{timeframe} RSI({RSI_PERIOD})**: `{rsi_value:.2f}` (≥ 85 极度超买)\n"
            f"💡 **建议操作**: 建议选择买入 **【下跌】** 事件合约"
        )
        send_telegram(msg)

    elif rsi_value <= 15:
        last_alert_times[timeframe] = now_ts
        msg = (
            f"🚨 **BTCUSDT 事件合约【{timeframe} 周期】超卖预警**\n"
            f"⏰ **北京时间**: `{bj_time}`\n"
            f"💰 **当前价格**: `{current_price:.2f}`\n"
            f"📊 **{timeframe} RSI({RSI_PERIOD})**: `{rsi_value:.2f}` (≤ 15 极度超卖)\n"
            f"💡 **建议操作**: 建议选择买入 **【上涨】** 事件合约"
        )
        send_telegram(msg)

def on_message(ws, message):
    data = json.loads(message)
    if 'data' not in data or 'k' not in data['data']:
        return

    kline = data['data']['k']
    close_price = float(kline['c'])
    is_closed = kline['x']
    interval = kline['i']

    if interval == '1m':
        # 1. 计算 1m 实时 RSI (包含未完结的实时跳动价格)
        curr_1m = klines_1m + [close_price]
        rsi_1m = calculate_rsi(curr_1m)
        check_and_notify("1m", close_price, rsi_1m)

        # 2. 计算 10m 实时 RSI
        curr_10m = klines_10m + [close_price]
        rsi_10m = calculate_rsi(curr_10m)
        check_and_notify("10m", close_price, rsi_10m)

        if is_closed:
            klines_1m.append(close_price)
            if len(klines_1m) > 100:
                klines_1m.pop(0)

            # 聚合 10m 收盘价
            temp_1m_buffer.append(close_price)
            if len(temp_1m_buffer) >= 10:
                klines_10m.append(close_price)
                temp_1m_buffer.clear()
                if len(klines_10m) > 100:
                    klines_10m.pop(0)

    elif interval == '1h':
        # 3. 计算 1h 实时 RSI
        curr_1h = klines_1h + [close_price]
        rsi_1h = calculate_rsi(curr_1h)
        check_and_notify("1h", close_price, rsi_1h)

        if is_closed:
            klines_1h.append(close_price)
            if len(klines_1h) > 100:
                klines_1h.pop(0)

def on_error(ws, error):
    print(f"WebSocket 连接报错: {error}")

def on_close(ws, close_status_code, close_msg):
    print("WebSocket 连接断开，3秒后自动尝试重连...")
    time.sleep(3)
    start_websocket()

def start_websocket():
    # 使用 Binance 多路径流 (Multiplexed Streams)，同时订阅 1m 和 1h 实时数据
    # 采用标准 Spot 实时流节点，防封禁与防防火墙能力最佳
    ws_url = "wss://stream.binance.com:9443/stream?streams=btcusdt@kline_1m/btcusdt@kline_1h"
    
    ws = websocket.WebSocketApp(
        ws_url,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws.run_forever()

# 保活 HTTP 响应服务（防止 Render 免费版因为无端口监听导致部署失败）
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Binance RSI Monitor Running")

def run_http_server():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

if __name__ == "__main__":
    print(f"[{get_beijing_time()}] 🚀 启动 BTCUSDT 多周期(1m/10m/1h) RSI 监控程序...")
    
    # 1. 预加载历史 K 线
    fetch_initial_klines()
    
    # 2. 启动 Render 保活 HTTP 服务
    threading.Thread(target=run_http_server, daemon=True).start()
    
    # 3. 开启 WebSocket 极速推送监听
    start_websocket()
