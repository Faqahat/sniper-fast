#!/usr/bin/env python3
# Owner 10-24 04:35 PKT: "check haqq specifically, also notice how he is sizing his trades according to tokens".
# Every haqqiUUX trade in the collector window (phaseA_r3comp, tokens launched after the extraction start): per buy its size and the
# context at that moment — the trade right before it (a dump? its size / drop), curve vSOL (market cap), token age, buys/sells so far,
# its open position on the token — plus per-token round trips (all buys vs all sells, FIFO P&L). Then: what the size follows.
import os, sys, json, collections, statistics
os.environ["RP_PHASEA_R3"] = os.environ.get("RP_PHASEA_R3", "phaseA_r3comp"); os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd")
os.environ.update(SELL_LAT="75", DIP_LATS="35,50,75", DIP_B="0.35", DIP_COHORT_FILE="/home/moiz/sniper/ops/overnight/sel/cohort_train.json")
D = "/home/moiz/sniper/ops/overnight/sel"; sys.path.insert(0, D)
import numpy as np
import selexit2 as X
W = sys.argv[1] if len(sys.argv) > 1 else "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
T0 = int(os.environ.get("EXTRACT_T0", "1792787700"))
recent = {m for m, c in X.L.items() if c["run"] == "R3" and c["bt"] >= T0 + 60}
byb = collections.defaultdict(set)
for m in recent: byb[("R3", X.rp.bucket(m))].add(m)
buys, tokens = [], []
for key in sorted(byb):
    for m, tr in X.rp.read_bucket(key[0], key[1], byb[key]).items():
        mine = [k for k, t in enumerate(tr) if t.get("user") == W]
        if not mine: continue
        S0 = X.L[m]["slot"]; pos_tok = 0; sol_in = sol_out = 0.0
        for k in mine:
            t = tr[k]
            if t["buy"]:
                prev = tr[k - 1] if k else None
                big = next((tr[j] for j in range(k - 1, max(-1, k - 40), -1) if not tr[j]["buy"] and tr[j]["sol"] >= 1e9 and X.arr(t) - X.arr(tr[j]) <= 1500), None)
                p_pre = (big["vsol"] + big["sol"]) / max(1, big["vtok"] - big["tok"]) if big else None
                buys.append(dict(m=m, sol=t["sol"] / 1e9, age=(t["s"] - S0) * X.SMS / 1000, vsol=(t["vsol"] - t["sol"]) / 1e9,
                                 dump=big["sol"] / 1e9 if big else 0.0, drop=(1 - (big["vsol"] / big["vtok"]) / p_pre) * 100 if big else 0.0,
                                 dt_ms=X.arr(t) - X.arr(big) if big else None, add=pos_tok > 0, nb=sum(1 for x in tr[:k] if x["buy"])))
                pos_tok += t["tok"]; sol_in += t["sol"] / 1e9
            else:
                pos_tok -= t["tok"]; sol_out += t["sol"] / 1e9
        nbuy = sum(1 for k in mine if tr[k]["buy"]); nsell = len(mine) - nbuy
        tokens.append(dict(m=m, nbuy=nbuy, nsell=nsell, sol_in=sol_in, sol_out=sol_out, open=pos_tok > 0.02 * max(1, sum(tr[k]["tok"] for k in mine if tr[k]["buy"])),
                           pnl=sol_out * (1 - 0.0125) - sol_in * (1 + 0.0125)))
json.dump(dict(buys=buys, tokens=tokens), open(f"{D}/haqq_sizing.json", "w"))
sz = [b["sol"] for b in buys]
print(f"{W[:8]}: {len(buys)} buys on {len(tokens)} tokens; size SOL median {statistics.median(sz):.3f}, p10 {np.percentile(sz, 10):.3f}, p90 {np.percentile(sz, 90):.3f}, max {max(sz):.3f}")
print(f"  first buy on a token {sum(1 for b in buys if not b['add'])}, adds to an open position {sum(1 for b in buys if b['add'])}; buys right after a >= 1 SOL dump (<= 1.5 s): {sum(1 for b in buys if b['dump'] > 0)}")
def corr(a, b): return float(np.corrcoef(a, b)[0, 1]) if len(a) > 2 else float("nan")
fb = [b for b in buys if not b["add"] and b["dump"] > 0]
if fb:
    s = np.array([b["sol"] for b in fb])
    for k in ("dump", "drop", "vsol", "age", "nb"):
        v = np.array([b[k] for b in fb], float); print(f"  first dip-buys: corr(size, {k:5s}) = {corr(s, v):+.2f}")
    r = s / np.array([b["dump"] for b in fb]); print(f"  size / dump size: median {np.median(r):.3f}, p25 {np.percentile(r, 25):.3f}, p75 {np.percentile(r, 75):.3f}")
    r2 = s / np.array([b["vsol"] for b in fb]); print(f"  size / curve vSOL: median {np.median(r2):.4f}, p25 {np.percentile(r2, 25):.4f}, p75 {np.percentile(r2, 75):.4f}")
    for lo, hi in ((1, 2), (2, 3), (3, 5), (5, 10), (10, 99)):
        v = [b["sol"] for b in fb if lo <= b["dump"] < hi]
        if v: print(f"  dump {lo}-{hi} SOL: {len(v):4d} buys, size median {statistics.median(v):.3f} SOL")
    for lo, hi in ((0, 5), (5, 10), (10, 15), (15, 25), (25, 60)):
        v = [b["sol"] for b in fb if lo <= b["drop"] < hi]
        if v: print(f"  drop {lo}-{hi}%: {len(v):4d} buys, size median {statistics.median(v):.3f} SOL")
    for lo, hi in ((0, 32), (32, 40), (40, 50), (50, 70), (70, 999)):
        v = [b["sol"] for b in fb if lo <= b["vsol"] < hi]
        if v: print(f"  curve vSOL {lo}-{hi}: {len(v):4d} buys, size median {statistics.median(v):.3f} SOL")
closed = [t for t in tokens if not t["open"]]
print(f"\nper token: {len(tokens)} tokens, closed {len(closed)}, win {100 * sum(1 for t in closed if t['pnl'] > 0) / max(1, len(closed)):.0f}%, P&L {sum(t['pnl'] for t in closed):+.2f} SOL;"
      f" buys per token median {statistics.median([t['nbuy'] for t in tokens]):.0f} (max {max(t['nbuy'] for t in tokens)}), sells per token median {statistics.median([t['nsell'] for t in tokens]):.0f}")
for lo, hi in ((0, 0.15), (0.15, 0.3), (0.3, 0.6), (0.6, 1.2), (1.2, 99)):
    v = [t for t in closed if lo <= t["sol_in"] < hi]
    if v: print(f"  SOL in per token {lo}-{hi}: {len(v):4d} tokens, win {100 * sum(1 for t in v if t['pnl'] > 0) / len(v):3.0f}%, P&L {sum(t['pnl'] for t in v):+6.2f}, avg {sum(t['pnl'] for t in v) / len(v):+.4f}")
