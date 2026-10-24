#!/usr/bin/env python3
# Does HkQ7hMjy sell on a take-profit / stop-loss / time rule? Local collector data only (R1 + R2).
# For each of its dip round trips (its buy right after a >=1 SOL sell, then its next own sell): the position value after
# every later trade = what its tokens would sell for at those reserves (pump curve, 1.25% fees) / the SOL it paid.
# Rule (TP, SL, T): decide at the first trade where value >= 1+TP or <= 1-SL, or once T slots have passed; the sell lands
# D slots after the decision slot. Match = predicted sell slot within +-1 slot of its real sell slot. Prints the best rules,
# the base rate (sell at its median hold), and what its value was in the slot before it sold (winners vs losers).
import sys, os, json, gzip, glob, collections, statistics, itertools
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry"); os.environ["RP_REPAIR"] = "0"
import rp
from multiprocessing import Pool
U = "HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ"
FEE = 0.0125
ms = set()
for f in glob.glob("/home/moiz/sniper/ops/overnight/census/parts/*.jsonl.gz"):
    for l in gzip.open(f, "rt"):
        if l[2:10] == "HkQ7hMjy": ms.add(json.loads(l)[1])
L = rp.load_launches()
byb = collections.defaultdict(set)
for m in ms:
    if m in L: byb[(L[m]["run"], rp.bucket(m))].add(m)
def val(tok, vsol, vtok):
    out = vsol * tok / (vtok + tok)
    return out * (1 - FEE)
def work(key):
    run, b = key; out = []
    for m, tr in rp.read_bucket(run, b, byb[key]).items():
        mine = [k for k, t in enumerate(tr) if t["user"] == U]
        for k in mine:
            t = tr[k]
            if not t["buy"] or k == 0: continue
            pv = tr[k - 1]
            if pv["buy"] or pv["sol"] < 1e9: continue
            ks = next((j for j in mine if j > k and not tr[j]["buy"]), None)
            if ks is None: continue
            # its other buys during the hold (adds) would change the position; keep simple trips only
            if any(tr[j]["buy"] for j in mine if k < j < ks): continue
            cost = t["sol"] * (1 + FEE)
            path = [(z["s"] - t["s"], val(t["tok"], z["vsol"], z["vtok"]) / cost, int(z["buy"]), z["sol"] / 1e9) for z in tr[k + 1:ks]]
            x = tr[ks]
            out.append(dict(m=m, hold=x["s"] - t["s"], real=x["sol"] * (1 - FEE) / cost, full=x["tok"] == t["tok"], path=path))
    return out
if __name__ == "__main__":
    R = []
    with Pool(6) as p:
        for o in p.imap_unordered(work, sorted(byb)): R += o
    R = [r for r in R if r["full"]]
    json.dump(R, open("/home/moiz/sniper/ops/overnight/hkq7/hk_paths.json", "w"))
    n = len(R); H = [r["hold"] for r in R]
    print(f"simple full round trips: {n}; hold median {statistics.median(H)} slots, p25 {statistics.quantiles(H, n=4)[0]:.0f}, p75 {statistics.quantiles(H, n=4)[2]:.0f}")
    hc = collections.Counter(H)
    print("hold histogram (slots: count):", ", ".join(f"{h}:{hc[h]}" for h in range(0, 31)))
    med = statistics.median(H)
    print(f"base rate: sell at its median hold ({med}) +-1 slot matches {sum(1 for h in H if abs(h - med) <= 1) / n:.0%}")
    def pred(r, tp, sl, T, D):
        for s, v, _, _ in r["path"]:
            if s >= T: return T + D
            if v >= 1 + tp or v <= 1 - sl: return s + D
        return min(T, 10 ** 6) + D if T < 10 ** 6 else None
    res = []
    TPS = (0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.12, 0.15, 0.20, 0.30, 9.0)
    SLS = (0.02, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30, 9.0)
    TS = (4, 6, 8, 10, 12, 15, 20, 25, 30, 40, 60, 10 ** 6)
    for tp, sl, T, D in itertools.product(TPS, SLS, TS, (0, 1, 2)):
        hit = 0
        for r in R:
            p = pred(r, tp, sl, T, D)
            if p is not None and abs(p - r["hold"]) <= 1: hit += 1
        res.append((hit / n, tp, sl, T, D))
    res.sort(reverse=True)
    print("best rules (match share, TP, SL, max hold slots, landing delay slots):")
    for x in res[:15]: print(f"  {x[0]:.0%}  TP {x[1]:g}  SL {x[2]:g}  T {x[3] if x[3] < 10 ** 6 else 'none'}  D {x[4]}")
    # value in the last trade before it sold, winners vs losers
    last = [(r["path"][-1][1] if r["path"] else 1.0, r) for r in R]
    for lab, g in (("sold up (real >= 1.0)", [v for v, r in last if r["real"] >= 1.0]), ("sold down (real < 1.0)", [v for v, r in last if r["real"] < 1.0])):
        if g: print(f"{lab}: n {len(g)}; position value at the last trade before its sell: p10 {statistics.quantiles(g, n=10)[0]:.3f} median {statistics.median(g):.3f} p90 {statistics.quantiles(g, n=10)[8]:.3f}")
    # for winners: how soon after the value first crossed +X did it sell?
    for X in (0.03, 0.05, 0.08, 0.10):
        d = []
        for r in R:
            c = next((s for s, v, _, _ in r["path"] if v >= 1 + X), None)
            if c is not None: d.append(r["hold"] - c)
        if d: print(f"trips whose value crossed +{X:.0%}: {len(d)} ({len(d) / n:.0%}); slots from the first crossing to its sell: median {statistics.median(d)}, within 2 slots {sum(1 for x in d if x <= 2) / len(d):.0%}")
    for X in (0.03, 0.05, 0.10, 0.15):
        d = []
        for r in R:
            c = next((s for s, v, _, _ in r["path"] if v <= 1 - X), None)
            if c is not None: d.append(r["hold"] - c)
        if d: print(f"trips whose value fell below -{X:.0%}: {len(d)} ({len(d) / n:.0%}); slots from the first drop to its sell: median {statistics.median(d)}, within 2 slots {sum(1 for x in d if x <= 2) / len(d):.0%}")
