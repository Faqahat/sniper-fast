#!/usr/bin/env python3
# Is "arrival ~ block position" usable? Compare, for trades our shadow engine logged with a real arrival time (outs, ms after the
# create was seen), the proxy arrival (index / block size x 212 ms, relative to the create's own proxy) with the real one.
import sys, os, json, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry"); os.environ["RP_REPAIR"] = "0"
import rp
from multiprocessing import Pool
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize2.json")).items()}
L = rp.load_launches(); O = rp.load_obs()
ms = [m for m, c in L.items() if c["run"] == "R2" and m in O and O[m]["outs"]]
byb = collections.defaultdict(set)
for m in ms[:6000]: byb[rp.bucket(m)].add(m)
def arr(s, i): return s * rp.SLOT_MS + i / max(SS.get(s, 400), i + 1) * rp.SLOT_MS
def work(b):
    out = []
    tra = rp.read_bucket("R2", b, byb[b])
    for m, tr in tra.items():
        c = L[m]; S = c["slot"]; ci = c.get("idx") or 0; a_c = arr(S, ci); used = set()
        for ms_, sol, isbuy, w6 in sorted(O[m]["outs"]):
            for k, t in enumerate(tr):
                if k in used or not t["user"].startswith(w6) or t["s"] - S > 3: continue
                if isbuy and sol > 0 and abs(t["sol"] / 1e9 - sol) > max(0.02, 0.15 * sol): continue
                used.add(k); out.append((ms_, arr(t["s"], t["i"]) - a_c, t["s"] - S)); break
    return out
if __name__ == "__main__":
    res = []
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(byb)): res += o
    print("matched trades", len(res))
    real = [r[0] for r in res]; prox = [r[1] for r in res]
    mr, mp = statistics.mean(real), statistics.mean(prox)
    cov = sum((a - mr) * (b - mp) for a, b in zip(real, prox)) / len(res)
    print(f"corr {cov / (statistics.pstdev(real) * statistics.pstdev(prox)):.3f}; proxy - real (ms): median {statistics.median(b - a for a, b in zip(real, prox)):+.1f}")
    for lo, hi in ((0, 25), (25, 50), (50, 75), (75, 100), (100, 150), (150, 250), (250, 500)):
        d = [b - a for a, b in zip(real, prox) if lo <= a < hi]
        if len(d) > 30:
            d.sort(); n = len(d); print(f"  real [{lo},{hi}) ms: n {n} proxy-real p10 {d[n // 10]:+.0f} median {d[n // 2]:+.0f} p90 {d[9 * n // 10]:+.0f}")
    # ordering agreement: pairs of trades, does proxy order = real order?
    import random
    rnd = random.Random(1); agree = tot = 0
    for _ in range(20000):
        a, b = rnd.choice(res), rnd.choice(res)
        if abs(a[0] - b[0]) < 20: continue
        tot += 1; agree += ((a[0] < b[0]) == (a[1] < b[1]))
    print(f"pairwise order agreement (real gap >= 20 ms): {agree / tot:.1%}")
