#!/usr/bin/env python3
# VALIDATION 4 (read-only): does our place-in-line model give the RIGHT FILL PRICE? For every outside BUY our engine saw
# (arrival ms m, matched to its chain trade), put a model buy at m ms with place() (built WITHOUT that tx) and compare the
# curve price we would fill at vs the price that tx really filled at (state just before it on chain). Ratio 1.00 = exact.
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
        c = L[m]; S = c["slot"]; st = rp.structure(tr, c); outs = O[m]["outs"]
        cand = [(k, t) for k, t in enumerate(tr) if k >= st["g_end"] and t["s"] - S <= 6 and t["user"] not in st["insiders"]]
        used = set(); matched = []
        for ms, sol, isbuy, w6 in sorted(outs):
            for k, t in cand:
                if k in used or t["buy"] != isbuy or not t["user"].startswith(w6): continue
                if isbuy and sol > 0 and abs(t["sol"] / 1e9 - sol) > max(0.02, 0.15 * sol): continue
                used.add(k); matched.append((ms, k, isbuy, w6)); break
        for ms, k, isbuy, w6 in matched:
            if not isbuy or ms > 300: continue
            others = [o for o in outs if not (o[3] == w6 and abs(o[0] - ms) < 1e-6)]
            path = tr[:k] + tr[k + 1:]
            idx, na = rp.place(path, c, rp.structure(path, c), others, ms)
            pp = (path[idx - 1]["vsol"] / path[idx - 1]["vtok"]) if idx > 0 else None
            pa = (tr[k - 1]["vsol"] / tr[k - 1]["vtok"]) if k > 0 else None
            if pp and pa: out.append((ms, pp / pa, tr[k]["s"] - S))
    return out
if __name__ == "__main__":
    res = []
    with Pool(14) as p:
        for o in p.imap_unordered(work, sorted(byb)): res += o
    r = [x[1] for x in res]
    q = lambda v, p: sorted(v)[int(p * (len(v) - 1))]
    print(f"outside buys checked: {len(res)}; model fill price / real fill price: median {statistics.median(r):.4f}, mean {statistics.mean(r):.4f}, p10 {q(r, .1):.4f}, p90 {q(r, .9):.4f}; within 2% {sum(1 for x in r if abs(x - 1) <= .02) / len(r):.0%}, within 5% {sum(1 for x in r if abs(x - 1) <= .05) / len(r):.0%}")
    for lo, hi in ((0, 50), (50, 100), (100, 300)):
        v = [x[1] for x in res if lo <= x[0] < hi]
        if v: print(f"   arrived {lo}-{hi} ms: n {len(v)} median {statistics.median(v):.4f} mean {statistics.mean(v):.4f} within 5% {sum(1 for x in v if abs(x - 1) <= .05) / len(v):.0%}")
