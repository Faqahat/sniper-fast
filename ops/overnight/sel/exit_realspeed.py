#!/usr/bin/env python3
# Owner 10-24 05:20 PKT (TP potential): which exit is best at OUR real landing? STRICT picks (score >= top2) of the TEST hours
# (12.3 h, never seen), entry 75 / 110 ms, guard 1.05, 0.35 SOL, all 192 exits of live_exits (TP x SL x time limit; TP/SL checks
# after each trade, sell lands next slot), the study's follower model. Uses size_reentry_test.json for the strict pick list.
import os, sys, json, collections
os.environ.update(RP_PHASEA_R2="phaseA_sel", SELL_LAT="75", SLIPIMP="1", DIP_REAL_SLIP="1", SEL_SLIP="1", DIP_LATS="35,50,75", DIP_B="0.35")
D = "/home/moiz/sniper/ops/overnight/sel"; sys.path.insert(0, D)
import numpy as np
import selexit2 as X
import live_exits as LE
from multiprocessing import Pool
M = json.load(open(f"{D}/IMIT1.json")); TOP2 = M["thresholds"]["top2"]
picks = [o for o in json.load(open(f"{D}/size_reentry_test.json")) if o["score"] >= TOP2]
need = collections.defaultdict(set)
for o in picks: need[o["m"]].add(o["age"])
byb = collections.defaultdict(set)
for m in need: byb[(X.L[m]["run"], X.rp.bucket(m))].add(m)
LATS = (75, 110); GUARD = 1.05
def det(tr, k, L):
    t = tr[k]; a0 = X.arr(t); fr = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4; p_after = t["vsol"] / t["vtok"]
    ke = k + 1
    while ke < len(tr) and X.arr(tr[ke]) < a0 + L: ke += 1
    if ke >= len(tr): return None
    if (tr[ke - 1]["vsol"] / tr[ke - 1]["vtok"]) / p_after > GUARD: return {"f": 0}
    s_in, S_, K_, VAL, CHK, PNL = X.rt_path(tr, ke, fr, int((a0 + L) // X.SMS)); n = len(K_); out = {"f": 1}
    for nm, tp, sl, cap, mh in LE.EXITS:
        co = s_in + cap; win = (S_ + 1 < co) & (S_ + 1 >= s_in + mh)
        ti = np.flatnonzero(CHK & (VAL >= 1 + tp) & win); si = np.flatnonzero(CHK & (VAL <= 1 - sl) & win)
        a = int(ti[0]) if len(ti) else None; b = int(si[0]) if len(si) else None
        s_out = co if (a is None and b is None) else (int(S_[a]) + 1 if (b is None or (a is not None and a <= b)) else int(S_[b]) + 1)
        out[nm] = float(PNL[min(int(np.searchsorted(K_, 2 * s_out + 1, side="left")), n)])
    return out
def work(key):
    run, b = key; out = []
    for m, tr in X.rp.read_bucket(run, b, byb[key]).items():
        S0 = X.L[m]["slot"]; done = set()
        for k, t in enumerate(tr):
            if t["buy"] or t["sol"] < X.MIN_SELL or t.get("syn"): continue
            age = round((t["s"] - S0) * X.SMS / 1000, 2)
            if age not in need[m] or age in done: continue
            done.add(age); out.append({L: det(tr, k, L) for L in LATS})
    return out
if __name__ == "__main__":
    R = []
    with Pool(6) as p:
        for o in p.imap_unordered(work, sorted(byb), chunksize=2): R += o
    print(f"strict TEST picks priced: {len(R)} of {len(picks)} (12.3 h), 0.35 SOL, guard 1.05")
    for L in LATS:
        agg = {}
        for nm, *_ in LE.EXITS:
            v = [r[L] for r in R if r.get(L) is not None]; fills = [x[nm] for x in v if x["f"]]; sk = sum(1 for x in v if not x["f"])
            agg[nm] = (sum(fills) - 0.0005 * sk, len(fills), sum(1 for x in fills if x > 0))
        top = sorted(agg, key=lambda n: -agg[n][0])
        print(f"\nat {L} ms — current exit TP +5% / SL -10% / 1.3 s: {agg['tp5_sl10_1.3s'][0]:+.3f} ({agg['tp5_sl10_1.3s'][2]}/{agg['tp5_sl10_1.3s'][1]} won); rank {top.index('tp5_sl10_1.3s') + 1}/192")
        for nm in ("tpnone_slnone_1.3s", "tpnone_sl10_1.3s", "tp10_sl10_1.3s", "tp20_sl10_1.3s", "tpnone_slnone_2s", "tpnone_sl10_2s", "tp20_sl10_4s", "tpnone_slnone_4s", "tpnone_slnone_6s"):
            if nm in agg: print(f"   {LE.label(nm):30s} {agg[nm][0]:+.3f} ({agg[nm][2]}/{agg[nm][1]} won)")
        print("   top 8:", "; ".join(f"{LE.label(n)} {agg[n][0]:+.3f}" for n in top[:8]))
