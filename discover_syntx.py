# discover_syntx.py
import MetaTrader5 as mt5
import re, sys

if not mt5.initialize():
    print("MT5 initialize failed:", mt5.last_error())
    sys.exit(1)

symbols = mt5.symbols_get()
pattern = re.compile(r'(vol|pain|gain|synt|fx|flip|break|trend|switch|sfx)', re.IGNORECASE)

candidates = []
for s in symbols:
    try:
        name = s.name
        desc = getattr(s, "description", "") or ""
        if pattern.search(name) or pattern.search(desc):
            candidates.append(name)
    except Exception:
        continue

if not candidates:
    print("No candidate SyntX-like symbols found. Make sure MT5 is logged in and Market Watch shows SyntX instruments.")
else:
    print("Found candidate SyntX-like symbols:")
    for n in sorted(set(candidates)):
        print("  -", n)

mt5.shutdown()
