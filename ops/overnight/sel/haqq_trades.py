#!/usr/bin/env python3
# Owner 10-24 05:45 PKT: haqqiUUX's most profitable tokens have many buys and sells — "what exactly did he do?". For each token
# (collector tape): every haqq trade in order with the token's state at that moment: age, market cap, his position, what came
# right before a buy (a dump: size / drop / ms before; or a pump) and a sell (run-up since his entry), FIFO realized P&L.
# usage: RP_PHASEA_R3=phaseA_r3hq python3 -I haqq_trades.py <mint> ...
import os, sys, json, datetime as dt
os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd")
os.environ.update(SELL_LAT="75", DIP_LATS="35,50,75", DIP_B="0.35", DIP_COHORT_FILE="/home/moiz/sniper/ops/overnight/sel/cohort_train.json")
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import selexit2 as X
W = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"; US = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"; SOLUSD = float(os.environ.get("SOLUSD", "102"))
PKT = dt.timezone(dt.timedelta(hours=5))
mc = lambda t: t["vsol"] / t["vtok"] * 1e6 * SOLUSD / 1000          # market cap after the trade, k$ (1B tokens, 6 decimals)
for m in sys.argv[1:]:
    L = X.L.get(m); tr = X.rp.read_bucket(L["run"], X.rp.bucket(m), {m}).get(m) if L else None
    if not tr: print(f"\n{m}: no tape"); continue
    S0 = L["slot"]; mine = [k for k, t in enumerate(tr) if t.get("user") == W]
    if not mine: print(f"\n{m}: no haqq trades on the tape"); continue
    peak = max(mc(t) for t in tr); kp = max(range(len(tr)), key=lambda k: mc(tr[k]))
    print(f"\n=== {m}  launched {dt.datetime.fromtimestamp(L['bt'], PKT):%H:%M:%S} PKT | trades {len(tr)} | peak MC ${peak:.1f}K at age {(tr[kp]['s'] - S0) * X.SMS / 1000:.0f}s | haqq trades {len(mine)}"
          + (f" | WE traded it too" if any(t.get('user') == US for t in tr) else ""))
    pos_tok = 0; cost = 0.0; realized = 0.0; first_t = None
    for k in mine:
        t = tr[k]; age = (t["s"] - S0) * X.SMS / 1000; bt = t.get("bt") or (L["bt"] + age)
        when = dt.datetime.fromtimestamp(bt, PKT).strftime("%H:%M:%S")
        if first_t is None: first_t = age
        if t["buy"]:
            big = next((tr[j] for j in range(k - 1, max(-1, k - 30), -1) if not tr[j]["buy"] and tr[j]["sol"] >= 0.5e9 and X.arr(t) - X.arr(tr[j]) <= 2000), None)
            ctx = ""
            if big:
                p_pre = (big["vsol"] + big["sol"]) / max(1, big["vtok"] - big["tok"]); drop = (1 - (big["vsol"] / big["vtok"]) / p_pre) * 100
                ctx = f"after a {big['sol'] / 1e9:.2f} SOL dump (-{drop:.0f}%) {X.arr(t) - X.arr(big):.0f} ms before"
            else:
                prev = tr[k - 1] if k else None
                ctx = f"no dump just before; previous trade {'buy' if prev and prev['buy'] else 'sell'} {prev['sol'] / 1e9:.2f}" if prev else ""
            pos_tok += t["tok"]; cost += t["sol"] / 1e9
            print(f"  {when} age {age:6.1f}s BUY  {t['sol'] / 1e9:6.3f} SOL @ MC ${mc(t):6.1f}K (peak so far ${max(mc(x) for x in tr[:k + 1]):.1f}K) | holds {pos_tok / 1e12:6.2f}M tok | {ctx}")
        else:
            frac = min(1.0, t["tok"] / max(1, pos_tok)); c = cost * frac; pnl = t["sol"] / 1e9 - c
            realized += pnl; cost -= c; pos_tok = max(0, pos_tok - t["tok"])
            runup = ""
            lb = next((tr[j] for j in range(k - 1, -1, -1) if tr[j].get("user") == W and tr[j]["buy"]), None)
            if lb: runup = f"MC {100 * (mc(t) / mc(lb) - 1):+.0f}% vs his last buy, {(X.arr(t) - X.arr(lb)) / 1000:.1f}s later"
            print(f"  {when} age {age:6.1f}s SELL {t['sol'] / 1e9:6.3f} SOL @ MC ${mc(t):6.1f}K | {100 * frac:3.0f}% of position | P&L {pnl:+.3f} SOL | {runup}")
    print(f"  -> realized {realized:+.3f} SOL (before pump fees ~1.25%/side), still holding {pos_tok / 1e12:.2f}M tokens; first trade at age {first_t:.0f}s")
