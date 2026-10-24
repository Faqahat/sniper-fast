#!/usr/bin/env python3
# VALIDATION 1 (read-only): is our trade data complete enough for an exact replay? For every launch, each trade's
# pre-trade reserves (previous event's post-trade reserves) + its own amounts must give exactly its post-trade reserves.
# A gap = a missing trade in our data (replay of later trades would be off). Reports the share of launches with gaps in
# the first 60 s / 10 min of trading.
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
L = rp.load_launches(); O = rp.load_obs()
fw = [m for m in O if m in L and L[m]["run"] == "R2" and "InitializeMayhemState" not in (L[m].get("ixn") or [])]
byb = collections.defaultdict(set)
for m in fw: byb[rp.bucket(m)].add(m)
def work(b):
    tr_all = rp.read_bucket("R2", b, byb[b]); out = []
    for m, tr in tr_all.items():
        c = L[m]; S = c["slot"]; gap60 = gap10m = 0; n60 = 0
        for a, t in zip(tr, tr[1:]):
            V, T = a["vsol"], a["vtok"]
            if not V or not T: continue
            if t["buy"]: exp_V = V + t["sol"]; exp_T = T - T * t["sol"] // (V + t["sol"]) if (V + t["sol"]) else T
            else: exp_V = V - V * t["tok"] // (T + t["tok"]) if (T + t["tok"]) else V; exp_T = T + t["tok"]
            ok = abs(exp_V - t["vsol"]) <= max(2, 1e-9 * V) + 1 and abs(exp_T - t["vtok"]) <= max(2, 1e-9 * T) + 1
            d = (t["s"] - S) * rp.SLOT_MS / 1000
            if d <= 60: n60 += 1; gap60 += not ok
            if d <= 600: gap10m += not ok
        out.append((m, len(tr), n60, gap60, gap10m, max(t["vsol"] for t in tr) > 200e9 or min(t["vsol"] for t in tr) < 25e9))
    return out
if __name__ == "__main__":
    res = []
    with Pool(14) as p:
        for o in p.imap_unordered(work, sorted(byb)): res += o
    sol = [r for r in res if not r[5]]
    print(f"launches with trades: {len(res)} (SOL-quoted, sane reserves: {len(sol)})")
    print(f"   any reserve gap in first 60 s: {sum(1 for r in sol if r[3]) / len(sol):.1%}; in first 10 min: {sum(1 for r in sol if r[4]) / len(sol):.1%}")
    gaps = sum(r[3] for r in sol); n = sum(r[2] for r in sol)
    print(f"   trades checked in first 60 s: {n}, mismatching: {gaps} ({gaps / max(1, n):.3%})")
    worst = sorted(sol, key=lambda r: -r[3])[:5]
    print("   worst:", [(r[0][:8], r[1], r[3]) for r in worst])
