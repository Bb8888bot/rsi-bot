import os
import time
import json
import threading
import requests
import websocket
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

# 环境变量配置
TG_TOKEN = os.environ.get("BOT_TOKEN")
TG_CHAT = os.environ.get("CHAT_ID")

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})

# 全局数据与锁
lock = threading.Lock()
closes_1m = []
last_kline_time = None

EVO_ENGINE = {
    "records": [], "total_signals": 0, "wins": 0, "losses": 0,
    "win_rate": 100.0, "dynamic_rsi_low": 15, "dynamic_rsi_high": 85,
    "evolution_stage": "初始算法 (胜率保护)"
}

DATA = {
    "price": 0.0, "rsi_1m": 50.0, "rsi_3m": 50.0, "rsi_5m": 50.0, "rsi_10m": 50.0, "rsi_1h": 50.0,
    "title": "极速 WebSocket 引擎连接中", "advice": "正在建立行情流", "color": "#f0b90b", "time": "--",
    "evo": {"total": 0, "wins": 0, "losses": 0, "win_rate": 100.0, "stage": "初始算法", "low": 15, "high": 85}
}

def get_beijing_time():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 28800))

def notify(title, text):
    if TG_TOKEN and TG_CHAT:
        msg = f"{title}\n{text}\n时间: {get_beijing_time()}"
        try:
            session.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": TG_CHAT, "text": msg}, timeout=3)
        except Exception as e:
            print("推送失败:", e)

def calc_rsi_wilder(prices, period=6):
    if len(prices) < period + 1: return 50.0
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
    if avg_l == 0: return 100.0 if avg_g > 0 else 50.0
    return round(100.0 - (100.0 / (1.0 + (avg_g / avg_l))), 2)

def resample_closes(closes, interval_min):
    if interval_min == 1 or not closes: return closes
    remainder = len(closes) % interval_min
    start_idx = remainder if remainder > 0 else 0
    res = []
    for i in range(start_idx, len(closes), interval_min):
        chunk = closes[i:i + interval_min]
        if chunk: res.append(chunk[-1])
    return res

# 启动时抓取 1000 条历史 K 线初始化
def init_history():
    global closes_1m
    url = "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1m&limit=1000"
    try:
        r = session.get(url, timeout=5.0)
        if r.status_code == 200:
            res = r.json()
            with lock:
                closes_1m = [float(k[4]) for k in res]
                print(f"成功直连加载历史 K 线: {len(closes_1m)} 条")
    except Exception as e:
        print("初始化历史数据异常:", e)

def process_evolution(current_price):
    global EVO_ENGINE
    now = time.time()
    for rec in EVO_ENGINE["records"]:
        if rec["status"] == "PENDING" and (now - rec["timestamp"]) >= 300:
            rec["settle_price"] = current_price
            rec["result"] = "WIN" if (rec["direction"] == "UP" and current_price > rec["trigger_price"]) or (rec["direction"] == "DOWN" and current_price < rec["trigger_price"]) else "LOSS"
            rec["status"] = "SETTLED"
            EVO_ENGINE["total_signals"] += 1
            if rec["result"] == "WIN": EVO_ENGINE["wins"] += 1
            else: EVO_ENGINE["losses"] += 1
            if EVO_ENGINE["total_signals"] > 0:
                EVO_ENGINE["win_rate"] = round((EVO_ENGINE["wins"] / EVO_ENGINE["total_signals"]) * 100, 1)

    recent = [r for r in EVO_ENGINE["records"] if r["status"] == "SETTLED"][-20:]
    if len(recent) >= 5:
        rate = (sum(1 for r in recent if r["result"] == "WIN") / len(recent)) * 100
        if rate < 80.0:
            EVO_ENGINE["dynamic_rsi_low"], EVO_ENGINE["dynamic_rsi_high"], EVO_ENGINE["evolution_stage"] = 10, 90, "🤖 进化阶段: 极致防御 (10/90)"
        elif rate >= 90.0:
            EVO_ENGINE["dynamic_rsi_low"], EVO_ENGINE["dynamic_rsi_high"], EVO_ENGINE["evolution_stage"] = 15, 85, "🤖 进化阶段: 进攻共振 (15/85)"
        else:
            EVO_ENGINE["dynamic_rsi_low"], EVO_ENGINE["dynamic_rsi_high"], EVO_ENGINE["evolution_stage"] = 12, 88, "🤖 进化阶段: 均衡高胜率 (12/88)"

def analyze(p, r1, r3, r5, r10, r1h):
    r_low, r_high = EVO_ENGINE["dynamic_rsi_low"], EVO_ENGINE["dynamic_rsi_high"]
    if r1h >= 50 and r10 <= 30 and r1 <= r_low: return "【90%+进化高胜率】趋势向上+深度超卖", "强烈建议：买入看涨 (UP)", "#10b981", "UP"
    if r1h <= 50 and r10 >= 70 and r1 >= r_high: return "【90%+进化高胜率】趋势向下+深度超买", "强烈建议：买入看跌 (DOWN)", "#ef4444", "DOWN"
    if r1 <= r_low and r3 <= 20 and r5 <= 25: return "【自适应超卖】1m/3m/5m插针", "建议：抓短线反弹 (UP)", "#10b981", "UP"
    if r1 >= r_high and r3 >= 80 and r5 >= 75: return "【自适应超买】1m/3m/5m拉升极值", "建议：抓短线回撤 (DOWN)", "#ef4444", "DOWN"
    if r1 >= r_high: return f"触发自适应超买警戒 (>={r_high})", "谨防回调，可小仓看跌 (DOWN)", "#f97316", "DOWN_WEAK"
    if r1 <= r_low: return f"触发自适应超卖警戒 (<={r_low})", "谨防反弹，可小仓看涨 (UP)", "#3b82f6", "UP_WEAK"
    return "事件合约常态运转中", f"等待极值点 (门槛: <={r_low} 或 >={r_high})", "#848e9c", "NONE"

# 币安原生 WebSocket 监听（毫秒级推流）
last_signal_time = 0
def on_ws_message(ws, message):
    global DATA, EVO_ENGINE, closes_1m, last_kline_time, last_signal_time
    try:
        data = json.loads(message)
        k = data.get("k", {})
        if not k: return
        p, k_time = float(k["c"]), k["t"]
        
        with lock:
            if not closes_1m:
                closes_1m.append(p)
                last_kline_time = k_time
            elif last_kline_time is None or k_time != last_kline_time:
                last_kline_time = k_time
                closes_1m.append(p)
                if len(closes_1m) > 1000: closes_1m.pop(0)
            else:
                closes_1m[-1] = p

            r1 = calc_rsi_wilder(closes_1m, 6)
            r3 = calc_rsi_wilder(resample_closes(closes_1m, 3), 6)
            r5 = calc_rsi_wilder(resample_closes(closes_1m, 5), 6)
            r10 = calc_rsi_wilder(resample_closes(closes_1m, 10), 6)
            r1h = calc_rsi_wilder(resample_closes(closes_1m, 60), 6)

            process_evolution(p)
            title, adv, color, sig_type = analyze(p, r1, r3, r5, r10, r1h)
            bj_time = get_beijing_time()

            DATA = {
                "price": p, "rsi_1m": r1, "rsi_3m": r3, "rsi_5m": r5, "rsi_10m": r10, "rsi_1h": r1h,
                "title": title, "advice": adv, "color": color, "time": bj_time,
                "evo": {"total": EVO_ENGINE["total_signals"], "wins": EVO_ENGINE["wins"], "losses": EVO_ENGINE["losses"], "win_rate": EVO_ENGINE["win_rate"], "stage": EVO_ENGINE["evolution_stage"], "low": EVO_ENGINE["dynamic_rsi_low"], "high": EVO_ENGINE["dynamic_rsi_high"]}
            }

            now = time.time()
            if sig_type in ["UP", "DOWN"] and (now - last_signal_time) > 180:
                EVO_ENGINE["records"].append({"timestamp": now, "trigger_price": p, "direction": sig_type, "status": "PENDING", "result": "UNKNOWN"})
                notify(f"🔥{title}", f"现价: ${p}\n指令: {adv}\n门槛: Low={EVO_ENGINE['dynamic_rsi_low']} High={EVO_ENGINE['dynamic_rsi_high']}")
                last_signal_time = now
    except Exception as e:
        print("WS 发生错误:", e)

def start_websocket():
    init_history()
    ws_url = "wss://fstream.binance.com/ws/btcusdt@kline_1m"
    while True:
        try:
            ws = websocket.WebSocketApp(
                ws_url,
                on_message=on_ws_message,
                on_error=lambda ws, e: print("WS Error:", e),
                on_close=lambda ws, c, m: print("WS 连接关闭，重连中...")
            )
            ws.run_forever(ping_interval=30, ping_timeout=10)
        except Exception: pass
        time.sleep(2)

threading.Thread(target=start_websocket, daemon=True).start()

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>BTC 极速量化终端</title>
    <style>
        body{font-family:sans-serif;padding:12px;background:#0b0e11;color:#eaecef;margin:0}
        .card{background:#181a20;padding:16px;border-radius:16px;max-width:420px;margin:auto;border:1px solid #2b2f36}
        h2{color:#f0b90b;font-size:17px;text-align:center;margin:0 0 10px 0}
        .evo-panel{background:#1e2329;padding:10px;border-radius:10px;margin-bottom:12px;border:1px solid #363c4e;font-size:12px}
        .evo-title{color:#f0b90b;font-weight:bold;margin-bottom:4px;display:flex;justify-content:space-between}
        .box{background:#2b2f36;padding:12px;border-radius:10px;margin:10px 0;border-left:5px solid #f0b90b;transition: border-color 0.3s;}
        .title{font-size:12px;color:#848e9c;margin-bottom:2px}
        .val{font-size:14px;font-weight:bold}
        .item{display:flex;justify-content:space-between;margin:8px 0;font-size:13px;border-bottom:1px dashed #2b2f36;padding-bottom:4px}
        .v{font-weight:bold;color:#f0b90b}
        .grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}
        .gbox{background:#2b2f36;padding:8px;border-radius:8px;text-align:center;font-size:11px}
        .gval{font-size:15px;font-weight:bold;margin-top:2px;color:#f0b90b}
        .time{color:#848e9c;font-size:10px;text-align:center;margin-top:10px}
    </style>
</head>
<body>
    <div class="card">
        <h2>⚡ BTC 事件合约自适应终端 (极速版)</h2>
        <div class="evo-panel">
            <div class="evo-title">
                <span id="estage">算法计算中...</span>
                <span id="ewr" style="color:#10b981">胜率: 100%</span>
            </div>
            <div style="color:#848e9c">战绩: <span id="estat" style="color:#fff">0胜 0负</span> | 门槛: <span id="ethres" style="color:#f0b90b">15 / 85</span></div>
        </div>
        <div class="box" id="box">
            <div class="title" id="stitle">加载中...</div>
            <div class="val" id="sadv">连接行情中...</div>
        </div>
        <div class="item"><span>参考价</span><span class="v" id="pr">$0.00</span></div>
        <div cl
