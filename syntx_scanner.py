# weltrade_syntx_scanner.py
import time, os
from datetime import datetime
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import requests
from dotenv import load_dotenv

load_dotenv()  # optional: store TELEGRAM_BOT_TOKEN & TELEGRAM_CHAT_ID in .env

# ================== CONFIG ==================
MT5_PATH = None  # optional: r"C:\Program Files\MetaTrader 5\terminal64.exe"

# Exact Weltrade Synthetics
SYMBOLS = [
    # GainX / PainX
    "GAIN","GANX","BDRY","DVOL",  # adjust PainX if needed

    # FX Vol
    "FX20","FX40","FX60","FX80","FX99",

    # SFX Vol
    "SFX20","SFX40","SFX60"
]

TIMEFRAME = mt5.TIMEFRAME_M1
BARS = 300
MA_FAST = 5
MA_SLOW = 15
LOOP_SLEEP = 1.0
SPIKE_MULTIPLIER = 2.0
MIN_SPIKE_PCT = 0.0005  # 0.05%
# ===========================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID")

# ----- MT5 initialization -----
def init_mt5():
    if MT5_PATH:
        ok = mt5.initialize(path=MT5_PATH)
    else:
        ok = mt5.initialize()
    if not ok:
        raise SystemExit(f"MT5 init failed: {mt5.last_error()}")
    print("MT5 initialized.")

def select_symbols(symbols):
    good = []
    for s in symbols:
        info = mt5.symbol_info(s)
        if info is None:
            print(f"Symbol not found: {s}")
            continue
        mt5.symbol_select(s, True)
        good.append(s)
    return good

# ----- Fetch bars -----
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
        return {"type":"MA_BUY", "price":float(last['close']), "time":last['time']}
    if sell:
        return {"type":"MA_SELL", "price":float(last['close']), "time":last['time']}

    return None

# ----- Telegram alerts -----
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
    global SYMBOLS
    SYMBOLS = select_symbols(SYMBOLS)
    if not SYMBOLS:
        print("No valid symbols selected. Exiting.")
        mt5.shutdown()
        return
    print("Monitoring Weltrade Synthetics:", SYMBOLS)

    seen = {s: None for s in SYMBOLS}
    try:
        while True:
            loop_start = time.time()
            for s in SYMBOLS:
                df = get_bars(s)
                if df.empty: continue
                sig = compute_signal(df)
                if sig:
                    stamp = str(sig.get("time"))
                    if seen[s] == stamp: continue
                    seen[s] = stamp
                    text = f"[{s}] {sig['type']} @ {sig.get('price')} (t={stamp})"
                    if 'pct' in sig:
                        text += f" pct={sig['pct']:.4f}"
                    print(text)
                    send_telegram(text)
            elapsed = time.time() - loop_start
            to_sleep = max(LOOP_SLEEP - elapsed, 0.1)
            time.sleep(to_sleep)
    except KeyboardInterrupt:
        print("Scanner stopped by user.")
    finally:
        mt5.shutdown()

if __name__ == "__main__":
    main()
