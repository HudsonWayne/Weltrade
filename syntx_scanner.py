# weltrade_syntx_scanner.py
import time, os
from datetime import datetime
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import requests

# ================== CONFIG ==================
MT5_PATH = None  # Optional MT5 terminal path
TIMEFRAME = mt5.TIMEFRAME_M1
BARS = 300
MA_FAST = 5
MA_SLOW = 15
LOOP_SLEEP = 1.0
SPIKE_MULTIPLIER = 2.0
MIN_SPIKE_PCT = 0.0005
RISK_PCT = 0.005  # 0.5% SL/TP

# Telegram alerts (optional)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID")
# ===========================================

# ----- MT5 Initialization -----
def init_mt5():
    if MT5_PATH:
        ok = mt5.initialize(path=MT5_PATH)
    else:
        ok = mt5.initialize()
    if not ok:
        raise SystemExit(f"MT5 init failed: {mt5.last_error()}")
    print("MT5 initialized.")

# ----- Auto-detect Weltrade Synthetics -----
def detect_syntx_symbols():
    all_symbols = mt5.symbols_get()
    syntx_keywords = ["GAIN","PAIN","FX","SFX","VOL","DVOL","BDRY","GANX"]
    available = []
    for s in all_symbols:
        if any(k in s.name.upper() for k in syntx_keywords):
            mt5.symbol_select(s.name, True)
            available.append(s.name)
    print("Monitoring Weltrade Synthetics:", available)
    return available

# ----- Fetch historical bars -----
def get_bars(symbol, n=BARS, timeframe=TIMEFRAME):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n)
    if rates is None or len(rates) == 0:
        return pd.DataFrame()
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

# ----- Compute signals -----
def compute_signal(df):
    if df.shape[0] < MA_SLOW + 5:
        return None
    df = df.copy()
    df['ma_fast'] = df['close'].rolling(MA_FAST).mean()
    df['ma_slow'] = df['close'].rolling(MA_SLOW).mean()
    df['pct'] = df['close'].pct_change()
    last = df.iloc[-1]; prev = df.iloc[-2]

    vol = df['pct'].std()
    spike_threshold = max(MIN_SPIKE_PCT, SPIKE_MULTIPLIER * vol)

    buy = (last['ma_fast'] > last['ma_slow']) and (prev['ma_fast'] <= prev['ma_slow'])
    sell = (last['ma_fast'] < last['ma_slow']) and (prev['ma_fast'] >= prev['ma_slow'])
    last_pct = last['pct'] if not np.isnan(last['pct']) else 0.0

    if abs(last_pct) >= spike_threshold:
        return {"type":"SPIKE_UP" if last_pct>0 else "SPIKE_DOWN",
                "price":float(last['close']),
                "pct":float(last_pct),
                "time":last['time']}
    if buy:
        return {"type":"BUY", "price":float(last['close']), "time":last['time']}
    if sell:
        return {"type":"SELL", "price":float(last['close']), "time":last['time']}
    return None

# ----- Calculate Stop-Loss & Take-Profit -----
def calculate_sl_tp(signal, df):
    entry = df['close'].iloc[-1]
    if signal['type'] in ['BUY','SPIKE_UP']:
        sl = entry * (1 - RISK_PCT)
        tp = entry * (1 + RISK_PCT*2)
    elif signal['type'] in ['SELL','SPIKE_DOWN']:
        sl = entry * (1 + RISK_PCT)
        tp = entry * (1 - RISK_PCT*2)
    else:
        sl, tp = entry, entry
    return round(sl,5), round(tp,5)

# ----- Format the signal nicely -----
def format_signal(symbol, sig, df):
    sl, tp = calculate_sl_tp(sig, df)
    text = f"🔹 {symbol} - {sig['type']}\n"
    text += f"   ⬆️ Entry: {sig['price']}\n"
    text += f"   🛑 Stop-Loss: {sl}\n"
    text += f"   🎯 Take-Profit: {tp}\n"
    if 'pct' in sig:
        text += f"   📊 Change%: {sig['pct']*100:.2f}%\n"
    text += f"   ⏱ Time: {sig['time']}\n"
    return text

# ----- Telegram alert -----
def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id":TELEGRAM_CHAT,"text":text}, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print("Telegram error:", e)
        return False

# ----- Main loop -----
def main():
    init_mt5()
    symbols = detect_syntx_symbols()
    if not symbols:
        print("No Weltrade Synthetics found. Check Market Watch.")
        mt5.shutdown()
        return

    seen = {s: None for s in symbols}
    try:
        while True:
            loop_start = time.time()
            for s in symbols:
                df = get_bars(s)
                if df.empty: continue
                sig = compute_signal(df)
                if sig:
                    stamp = str(sig.get("time"))
                    if seen[s] == stamp: continue
                    seen[s] = stamp
                    formatted = format_signal(s, sig, df)
                    print(formatted)
                    send_telegram(formatted)
            elapsed = time.time() - loop_start
            time.sleep(max(LOOP_SLEEP - elapsed, 0.1))
    except KeyboardInterrupt:
        print("Scanner stopped by user.")
    finally:
        mt5.shutdown()

if __name__ == "__main__":
    main()
