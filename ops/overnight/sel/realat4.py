#!/usr/bin/env python3
# Guard sweep at the real landing: the 407 TEST picks (sel_exitbt.py set), entry 75..150 ms, price guard 1.02..1.10 (the engine's
# min-out = quote / guard), exit TP +5% / SL -10% / 1.3 s, size 0.25; a guard-skipped pick costs 0.0005 SOL.
import os, sys, json, collections
os.environ.update(RP_PHASEA_R2="phaseA_sel", SELL_LAT="75", SLIPIMP="1", DIP_REAL_SLIP="1", SEL_SLIP="1", DIP_LATS="35,50,75", DIP_B="0.25")
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import numpy as np
import selexit2 as X
import live_exits as LE
from multiprocessing import Pool
LATS = (35, 75, 110, 125); GUARDS = (1.02, 1.03, 1.05, 1.08, 1.10); NM = "tp5_sl10_1.3s"; FAIL = 0.0005
EXI = [e for e in LE.EXITS if e[0] == NM][0]
def detail(tr, k, L, g):
    t = tr[k]; a0 = X.arr(t); fr = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4; p_after = t["vsol"] / t["vtok"]
    ke = k + 1
    while ke < len(tr) and X.arr(tr[ke]) < a0 + L: ke += 1
    if ke >= len(tr): return None
    if (tr[ke - 1]["vsol"] / tr[ke - 1]["vtok"]) / p_after > g: return 0
    s_land = int((a0 + L) // X.SMS)
    s_in, S_, K_, VAL, CHK, PNL = X.rt_path(tr, ke, fr, s_land)
    nm, tp, sl, cap, mh = EXI; n = len(K_)
    co = s_in + cap; win = (S_ + 1 < co) & (S_ + 1 >= s_in + mh)
    ti = np.flatnonzero(CHK & (VAL >= 1 + tp) & win); si = np.flatnonzero(CHK & (VAL <= 1 - sl) & win)
    a = int(ti[0]) if len(ti) else None; b = int(si[0]) if len(si) else None
    if a is None and b is None: s_out = co
    elif b is None or (a is not None and a <= b): s_out = int(S_[a]) + 1
    else: s_out = int(S_[b]) + 1
    j = min(int(np.searchsorted(K_, 2 * s_out + 1, side="left")), n)
    return [float(PNL[j])]
need = collections.defaultdict(set)
for l in open("/home/moiz/sniper/ops/overnight/sel/picks_imit1_top4_test.jsonl"):
    r = json.loads(l); need[r["m"]].add(r["age"])
byb = collections.defaultdict(set)
for m in need: byb[(X.L[m]["run"], X.rp.bucket(m))].add(m)
def work(key):
    run, b = key; out = []
    for m, tr in X.rp.read_bucket(run, b, byb[key]).items():
        S0 = X.L[m]["slot"]; done = set()
        for k, t in enumerate(tr):
            if t["buy"] or t["sol"] < X.MIN_SELL or t.get("syn"): continue
            age = round((t["s"] - S0) * X.SMS / 1000, 2)
            if age not in need[m] or age in done: continue
            done.add(age); out.append({(L, g): detail(tr, k, L, g) for L in LATS for g in GUARDS})
    return out
if __name__ == "__main__":
    R = []
    with Pool(6) as p:
        for o in p.imap_unordered(work, sorted(byb), chunksize=2): R += o
    print(f"TEST picks {len(R)} (12.3 h), 0.25 SOL, exit TP +5% / SL -10% / 1.3 s; P&L SOL (fills, won)")
    print("guard  " + "  ".join(f"{L:>22d} ms" for L in LATS))
    for g in GUARDS:
        row = []
        for L in LATS:
            v = [x[(L, g)] for x in R if x.get((L, g)) is not None]
            fills = [x[0] for x in v if x]; sk = sum(1 for x in v if x == 0)
            row.append(f"{sum(fills) - FAIL * sk:+7.3f} ({len(fills):3d}, {sum(1 for f in fills if f > 0):3d})")
        print(f"x{g:<5}" + "  ".join(f"{c:>25s}" for c in row))
