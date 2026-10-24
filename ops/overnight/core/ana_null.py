# NULL CHECK for the guarded quick flip: is the deployer list doing real work, or would any serial deployer do?
import sys, json, collections, random
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
L = rp.load_launches(); O = rp.load_obs()
ev = sorted((c["bt"], c["user"]) for c in L.values() if c.get("bt"))
nl = collections.Counter(); j = 0; prior = {}
for bt, m in sorted((c["bt"], m) for m, c in L.items() if c.get("bt") and c["run"] == "R2"):
    while j < len(ev) and ev[j][0] < bt: nl[ev[j][1]] += 1; j += 1
    prior[m] = nl[L[m]["user"]]
fw = [m for m in O if m in L and L[m]["run"] == "R2" and "InitializeMayhemState" not in (L[m].get("ixn") or [])]
byb = collections.defaultdict(set)
for m in fw: byb[rp.bucket(m)].add(m)
EX = [rp.R("hold1s", [(1.0, ("t", 1))], 2)]
def work(b):
    tra = rp.read_bucket("R2", b, byb[b]); fa = rp.read_failed("R2", b, byb[b]); out = {}
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]
        ib, _ = rp.place_bo2(tr, c, st, O[m]["outs"], 75, fa.get(m, []))
        if ib < 1: continue
        if (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b > 1.01: out[m] = -0.005
        else:
            o = rp.sim(tr, c, st, ib, 0.5, EX, fill_pen=0.015)
            if o: out[m] = o["hold1s"]["pnl"]
    return out
if __name__ == "__main__":
    res = {}
    with Pool(14) as p:
        for o in p.imap_unordered(work, sorted(byb)): res.update(o)
    NUL = dict(by_prior=[], random=[])
    for lo, hi in ((0, 0), (1, 2), (3, 9), (10, 49), (50, 10 ** 9)):
        v = [x for m, x in res.items() if lo <= prior[m] <= hi]
        NUL["by_prior"].append(dict(lo=lo, hi=hi, n=len(v), tot=sum(v)))
        print(f"guarded flip at 75 ms, ALL deployers with {lo}-{hi if hi < 10 ** 9 else 'inf'} prior launches seen: n {len(v):5} fills {sum(1 for x in v if x != -0.005):5} total {sum(v):+8.2f} SOL")
    # random deployer lists of the same size as S4's (~90 serial deployers), 20 draws
    deps = [d for d, n in nl.items() if n >= 3]
    random.seed(5); tots = []
    for _ in range(20):
        pick = set(random.sample(deps, 92)); v = [x for m, x in res.items() if L[m]["user"] in pick and prior[m] >= 1]
        tots.append(sum(v))
    print(f"20 random lists of 92 serial deployers: totals {sorted(round(t, 2) for t in tots)}")
    NUL["random"] = sorted(tots); json.dump(NUL, open("/home/moiz/sniper/ops/overnight/report/null.json", "w"))
