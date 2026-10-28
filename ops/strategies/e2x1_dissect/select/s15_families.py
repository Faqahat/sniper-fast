#!/usr/bin/env python3
"""SELECT s15: final family table (trip-based lot P&L from s2; pump.fun protocol+creator fees estimated from the tape fee_bps per row;
tx fees / tips NOT included -> recon's lamport reconciliation is the authority). Families (causal: age and trigger seen before his buy):
  first buy:  LAUNCH (<10 s) / EARLY (10-120 s) / LATE (2-30 min)  x  trigger DIP (biggest-impact trade in the 3 slots before him is a
              sell <= -5 %) / RIP (a buy >= +5 %) / FLOW (smaller)
  RE-ENTRY: buy after a closed trip on the same token (split by px vs his previous fill);  ADD: buy while still holding."""
import sys, pickle, collections, time, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select")
from lib import *
from tl import cols
D = load(); w = int(D["wid"])
X = cols(pickle.load(open(f"{OUT}/buys.pkl", "rb"))); S = pickle.load(open(f"{OUT}/speed.pkl", "rb"))
us = D["user"]; bu = D["buy"].astype(bool); tk = D["tok"].astype(np.float64); mi = D["mint"]; so = D["sol"] / 1e9
fee = so * (D["fee_bps"].astype(float) + D["cfee_bps"].astype(float)) / 1e4
my = np.flatnonzero(us == w); print(f"his rows {len(my)}  est. pump.fun fees {fee[my].sum():.2f} SOL (buys {fee[my][bu[my]].sum():.2f}, sells {fee[my][~bu[my]].sum():.2f})")
# per-lot fee: own buy fee + share of sells' fees ~ same rate -> approximate lot fee = 2 * sol * rate
rate = (D["fee_bps"][X["row"]].astype(float) + D["cfee_bps"][X["row"]].astype(float)) / 1e4
X["fee"] = 2 * X["sol"] * rate
held = np.zeros(len(X["row"]), bool); pos = collections.defaultdict(float); k_of = {int(r): k for k, r in enumerate(X["row"])}
for r in my:
    m = int(mi[r])
    if bu[r]:
        if r in k_of: held[k_of[r]] = pos[m] > 1e3
        pos[m] += tk[r]
    else: pos[m] = max(pos[m] - tk[r], 0)
ti = np.array([s.get("trg_imp", 0.0) for s in S]); tb = np.array([s.get("trg_buy", False) for s in S])
trg = np.where((ti <= -0.05) & ~tb, "DIP", np.where((ti >= 0.05) & tb, "RIP", "FLOW"))
age = X["age_s"]
stage = np.where(age < 10, "LAUNCH", np.where(age < 120, "EARLY", "LATE"))
prevpx = {}; ratio = np.full(len(X["row"]), np.nan)
for k in np.argsort(X["row"]):
    R = X["row"][k]; m = int(mi[R]); px = so[R] / tk[R]
    if m in prevpx: ratio[k] = px / prevpx[m] - 1
    prevpx[m] = px
fam = np.where(X["add"] == 0, np.char.add(np.char.add(stage, "-"), trg),
               np.where(held, "ADD-HOLDING", np.where(ratio < -0.1, "RE-ENTRY-DIP", np.where(ratio < 0.1, "RE-ENTRY-FLAT", "RE-ENTRY-HIGHER"))))
np.save(f"{OUT}/family.npy", fam)
days = (X["bt"].max() - X["bt"].min()) / 86400
tot = X["lot_pnl"].sum()
print(f"window {pkt(X['bt'].min())} .. {pkt(X['bt'].max())} PKT = {days:.2f} days; buys {len(fam)}; gross lot P&L {tot:.1f} SOL; minus est. pump fees {tot - X['fee'].sum():.1f}")
print(f"{'family':18s} {'buys':>5s} {'share':>6s} {'gross':>7s} {'net*':>7s} {'%P&L':>5s} {'/day':>6s} {'ret%':>6s} {'win':>4s} {'age_s':>6s} {'hold_s':>6s} {'unclosed':>8s}")
rows = []
for f in sorted(set(fam.tolist())):
    m = fam == f; g = X["lot_pnl"][m].sum(); n = g - X["fee"][m].sum()
    rows.append((f, int(m.sum()), g, n))
    print(f"{f:18s} {m.sum():5d} {m.mean():6.3f} {g:7.1f} {n:7.1f} {100*g/tot:5.1f} {n/days:6.2f} {100*np.mean(X['lot_pnl'][m]/X['sol'][m]):6.2f} {np.mean(X['lot_pnl'][m]>0):4.2f}"
          f" {np.median(age[m]):6.0f} {np.median(X['hold_s'][m]):6.0f} {int(X['unsold'][m].sum()):8d}")
day = np.array([time.strftime("%m-%d", time.gmtime(t + 18000)) for t in X["bt"]])
print("\nper day (gross / net*):", {d: (round(X['lot_pnl'][day == d].sum(), 1), round((X['lot_pnl'] - X['fee'])[day == d].sum(), 1)) for d in sorted(set(day))})
print("* net = gross minus estimated pump.fun fees only (no tx fees/tips); unclosed trips marked at the last curve px (graduated tokens sell on PumpSwap, outside this tape; matches recon exact on D0+D1 to 0.2%)")
