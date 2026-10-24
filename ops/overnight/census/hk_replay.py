#!/usr/bin/env python3
# Sanity check of our replay: re-simulate HkQ7hMjy's own round trips (buy right where it bought, sell at the state right before
# its own sell) with OUR curve math, its own trades removed, vs its real SOL in/out. Then the same entries with our H-slot exits.
import sys, os, json, gzip, glob, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry"); os.environ["RP_REPAIR"] = "0"
import rp
from multiprocessing import Pool
U = "HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ"
ms = set()
for f in glob.glob("/home/moiz/sniper/ops/overnight/census/parts/*.jsonl.gz"):
    for l in gzip.open(f, "rt"):
        if l[2:10] == "HkQ7hMjy": ms.add(json.loads(l)[1])
L = rp.load_launches()
byb = collections.defaultdict(set)
for m in ms: byb[(L[m]["run"], rp.bucket(m))].add(m)
def work(key):
    run, b = key; out = []
    tra = rp.read_bucket(run, b, byb[key])
    for m, tr in tra.items():
        for k, t in enumerate(tr):
            if t["user"] != U or not t["buy"]: continue
            ks = next((j for j in range(k + 1, len(tr)) if tr[j]["user"] == U), None)
            if ks is None or tr[ks]["buy"] or tr[ks]["tok"] != t["tok"]: continue      # simple full round trips only
            fr = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
            real = tr[ks]["sol"] * (1 - fr) / 1e9 - t["sol"] * (1 + fr) / 1e9
            # our replay: same buy SOL at the state before its buy, others' trades in between, sell before its sell
            V = t["vsol"] - t["sol"]; T = t["vtok"] + t["tok"]
            X = t["sol"]; q = T * X // (V + X); V += X; T -= q
            for x in tr[k + 1:ks]:
                if x["user"] == U: continue
                if x["buy"]: d = T * x["sol"] // (V + x["sol"]); V += x["sol"]; T -= d
                else: so = V * x["tok"] // (T + x["tok"]); V -= so; T += x["tok"]
            so = V * q // (T + q); sim = so * (1 - fr) / 1e9 - X * (1 + fr) / 1e9
            prev = tr[k - 1] if k > 0 else None
            out.append(dict(m=m, real=real, sim=sim, slots=tr[ks]["s"] - t["s"], after_big_sell=bool(prev and not prev["buy"] and prev["sol"] >= 1e9 and prev["s"] == t["s"]),
                            buy=t["sol"] / 1e9, first_in_slot=tr[ks - 1]["s"] < tr[ks]["s"]))
    return out
if __name__ == "__main__":
    res = []
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(byb)): res += o
    print("round trips", len(res))
    for nm, sub in (("all", res), ("after a big sell", [r for r in res if r["after_big_sell"]]), ("other entries", [r for r in res if not r["after_big_sell"]])):
        print(f"  {nm:18s} n {len(sub)} real mean {statistics.mean(r['real'] for r in sub):+.4f} sum {sum(r['real'] for r in sub):+.2f} | our sim mean {statistics.mean(r['sim'] for r in sub):+.4f} sum {sum(r['sim'] for r in sub):+.2f} | win real {sum(1 for r in sub if r['real'] > 0) / len(sub):.0%}")
    d = [r["sim"] - r["real"] for r in res]
    print(f"  sim - real: median {statistics.median(d):+.5f} mean {statistics.mean(d):+.5f}; sells first in their slot {sum(1 for r in res if r['first_in_slot']) / len(res):.0%}")
    hb = collections.Counter(min(r["slots"], 70) // 5 * 5 for r in res)
    print("  hold slots:", sorted(hb.items()))
    for lo, hi in ((0, 5), (5, 10), (10, 20), (20, 40), (40, 61), (61, 10 ** 6)):
        v = [r for r in res if lo <= r["slots"] < hi]
        if v: print(f"   hold [{lo},{hi}) n {len(v)} real mean {statistics.mean(r['real'] for r in v):+.4f} win {sum(1 for r in v if r['real'] > 0) / len(v):.0%}")
