#!/usr/bin/env python3
# VALIDATION 2 (read-only): does ARRIVAL TIME in our feed predict CHAIN POSITION? For every outside tx our engine saw
# (matched to its chain trade), predicted place = number of matched outside trades that arrived earlier; actual place =
# number of outside trades before it in chain order. If arrival order ~ chain order, placing our buy by our landing ms
# is honest. Also: arrival ms of txs that ended up in the create slot vs the next slot.
import sys, json, collections, statistics
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
        if min(t["vsol"] for t in tr) < 25e9: continue
        c = L[m]; S = c["slot"]; st = rp.structure(tr, c)
        cand = [(k, t) for k, t in enumerate(tr) if k >= st["g_end"] and t["s"] - S <= 6 and t["user"] not in st["insiders"]]
        pos = {k: n for n, (k, t) in enumerate(cand)}          # outside place in chain order
        used = set(); matched = []
        for ms, sol, isbuy, w6 in sorted(O[m]["outs"]):
            for k, t in cand:
                if k in used or t["buy"] != isbuy or not t["user"].startswith(w6): continue
                if isbuy and sol > 0 and abs(t["sol"] / 1e9 - sol) > max(0.02, 0.15 * sol): continue
                used.add(k); matched.append((ms, k, t["s"] - S)); break
        n_out = len(O[m]["outs"])
        for r, (ms, k, ds) in enumerate(matched):
            pred = sum(1 for ms2, k2, _ in matched if ms2 < ms)
            out.append((ms, pred, pos[k], ds, n_out, len(matched)))
    return out
if __name__ == "__main__":
    res = []
    with Pool(14) as p:
        for o in p.imap_unordered(work, sorted(byb)): res += o
    print(f"matched outside txs: {len(res)}")
    diff = [a - p for _, p, a, _, _, _ in res]
    print(f"   actual place - predicted place: exact {sum(1 for d in diff if d == 0) / len(diff):.0%}, within 1 {sum(1 for d in diff if abs(d) <= 1) / len(diff):.0%}, within 2 {sum(1 for d in diff if abs(d) <= 2) / len(diff):.0%}; mean {statistics.mean(diff):+.2f}")
    for lo, hi in ((0, 25), (25, 50), (50, 75), (75, 100), (100, 150), (150, 250), (250, 1000)):
        v = [r for r in res if lo <= r[0] < hi]
        if not v: continue
        d = [a - p for _, p, a, _, _, _ in v]
        print(f"   arrived {lo:3}-{hi:4} ms: n {len(v):6}  in create slot {sum(1 for r in v if r[3] == 0) / len(v):5.0%}  next slot {sum(1 for r in v if r[3] == 1) / len(v):4.0%}  | actual-predicted place: mean {statistics.mean(d):+.2f}, exact/within1 {sum(1 for x in d if x == 0) / len(d):.0%}/{sum(1 for x in d if abs(x) <= 1) / len(d):.0%}")
    json.dump(res[:200000], open("val_place.json", "w"))
