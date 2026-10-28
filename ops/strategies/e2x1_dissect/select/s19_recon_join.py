#!/usr/bin/env python3
"""SELECT s19: join my families (s15, 6.6 days, tape lot P&L) to recon's exact lots (D0+D1 = 10-26 20:00 -> 10-28 20:00 PKT,
pnl = all costs incl. tx fees/tips, open lots marked) by (slot, idx). Exact per-family P&L over recon's window, and entry speed to
recon's EXACT trigger (size equation): slot gap and chain-clock ms (slot*212 + idx/blocksize*212)."""
import sys, pickle, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select")
from lib import *
from tl import cols
L = pickle.load(open("/home/moiz/sniper-data/e2x1_dissect/recon/lots.pkl", "rb"))
X = cols(pickle.load(open(f"{OUT}/buys.pkl", "rb"))); fam = np.load(f"{OUT}/family.npy")
key = {(int(s), int(i)): k for k, (s, i) in enumerate(zip(X["slot"], X["idx"]))}
S = np.load(f"{TP}/slots.npy"); s0 = int(S["slot"].min())
bsz = np.full(int(S["slot"].max()) - s0 + 1, 400.0); bsz[S["slot"].astype(np.int64) - s0] = S["maxi"].astype(np.float64) + 1
def cc(s, i): return s * SMS + i / max(bsz[min(s - s0, len(bsz) - 1)], i + 1.0) * SMS
D0, D1 = 1793026800, 1793199600
W = [l for l in L if D0 <= l["bt"] < D1]
fm = collections.defaultdict(list); unmatched = []
for l in W:
    k = key.get((l["s"], l["i"]))
    (fm[fam[k]] if k is not None else unmatched).append(l)
tot = sum(l["pnl"] for l in W)
print(f"recon lots D0+D1 {len(W)}, exact P&L {tot:+.3f} SOL; matched to my tape {len(W) - len(unmatched)} (unmatched = after my tape end 10-28 18:41: {len(unmatched)}, P&L {sum(l['pnl'] for l in unmatched):+.3f})")
print(f"{'family':18s} {'lots':>5s} {'exact P&L':>10s} {'mSOL/lot':>9s} {'win':>5s} {'bots':s}")
for f in sorted(fm):
    v = fm[f]; p = np.array([l["pnl"] for l in v])
    print(f"{f:18s} {len(v):5d} {p.sum():+10.3f} {1000*p.mean():+9.1f} {np.mean(p>0):5.2f} {dict(collections.Counter(l['bot'] for l in v))}")
print("\nentry speed to the exact trigger (tiered lots):")
for b in ("FRESH", "MINUTE"):
    v = [l for l in W if l["bot"] == b and l.get("trig_slot_gap") is not None]
    g = np.array([l["trig_slot_gap"] for l in v])
    ms = []
    for l in v:
        ts = l["s"] - l["trig_slot_gap"]
        # trigger idx: same slot -> i - idx_gap; else unknown idx -> use the slot's end (conservative: shortest lag)
        ti = l["i"] - l["trig_idx_gap"] if l["trig_idx_gap"] is not None else bsz[min(ts - s0, len(bsz) - 1)] - 1
        ms.append(cc(l["s"], l["i"]) - cc(ts, ti))
    ms = np.array(ms)
    print(f"  {b}: n={len(v)}  same slot {np.mean(g==0):.2f}  +1 slot {np.mean(g==1):.2f}  >=2 {np.mean(g>=2):.2f} | lag ms p25 {np.percentile(ms,25):.0f} med {np.median(ms):.0f} p75 {np.percentile(ms,75):.0f} p90 {np.percentile(ms,90):.0f}"
          f" | trigger is a buy {np.mean([l['trig_buy'] for l in v]):.2f} | trades between trigger and him: med {np.median([l['n_between'] for l in v]):.0f}")
