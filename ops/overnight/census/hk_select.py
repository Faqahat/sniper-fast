#!/usr/bin/env python3
# Within the launches HkQ7hMjy traded: which big sells (>=1 SOL, age 1-60 s) did it backrun (its buy is the next trade in the
# same slot) and which not? Also replay its real round trips with our mechanics (sanity check of the replay).
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
    run, b = key; ev = []; rt = []
    tra = rp.read_bucket(run, b, byb[key])
    for m, tr in tra.items():
        c = L[m]; S = c["slot"]; st = rp.structure(tr, c)
        mine = [k for k, t in enumerate(tr) if t["user"] == U]
        if not mine: continue
        first, last = mine[0], mine[-1]
        for k, t in enumerate(tr):
            if t["buy"] or t["sol"] < 1e9 or k < st["g_end"] or k >= len(tr) - 1: continue
            age = (t["s"] - S) * rp.SLOT_MS / 1000
            if not (1 <= age <= 60): continue
            nx = tr[k + 1]; hit = nx["user"] == U and nx["buy"] and nx["s"] == t["s"]
            # features
            w20 = [x for x in tr[max(0, k - 40):k] if t["s"] - x["s"] <= 20]
            bsol = sum(x["sol"] for x in w20 if x["buy"]) / 1e9; ssol = sum(x["sol"] for x in w20 if not x["buy"]) / 1e9
            peak = max(x["vsol"] / x["vtok"] for x in tr[:k + 1]); p = t["vsol"] / t["vtok"]
            ge = tr[st["g_end"] - 1]; pb = ge["vsol"] / ge["vtok"]
            held = any(tr[j]["user"] == U and tr[j]["buy"] for j in range(first, k)) and not any(tr[j]["user"] == U and not tr[j]["buy"] for j in range(first, k))
            ev.append(dict(m=m, hit=hit, age=age, sell=t["sol"] / 1e9, ins=t["user"] in st["insiders"], vsol=t["vsol"] / 1e9, b20=bsol, s20=ssol,
                           dd=p / peak, pb=p / pb, nb=sum(1 for x in tr[:k] if x["buy"]), before_first=k < first, after_last=k > last, holding=held,
                           seller=t["user"][:8]))
        # its real round trips: buy at k, next own sell
        for i, k in enumerate(mine):
            t = tr[k]
            if not t["buy"]: continue
            ks = next((j for j in mine if j > k and not tr[j]["buy"]), None)
            if ks is None: continue
            rt.append(dict(m=m, buy_sol=t["sol"] / 1e9, sell_sol=tr[ks]["sol"] / 1e9, slots=tr[ks]["s"] - t["s"], tok_b=t["tok"], tok_s=tr[ks]["tok"]))
    return ev, rt
if __name__ == "__main__":
    EV = []; RT = []
    with Pool(8) as p:
        for e, r in p.imap_unordered(work, sorted(byb)): EV += e; RT += r
    hit = [e for e in EV if e["hit"]]; miss = [e for e in EV if not e["hit"]]
    inwin = [e for e in EV if not e["before_first"] and not e["after_last"]]
    print(f"big sells (>=1 SOL, age 1-60 s) in its launches: {len(EV)}; it backran {len(hit)} ({len(hit) / len(EV):.0%}); inside its active window: {len(inwin)}, backran {sum(1 for e in inwin if e['hit'])}")
    print(f"  backran while already holding: {sum(1 for e in hit if e['holding'])}")
    def cmp(name, f):
        a = [f(e) for e in hit]; b = [f(e) for e in miss]
        print(f"  {name:10s} backran median {statistics.median(a):8.3f} | not {statistics.median(b):8.3f}")
    for nm, f in (("age", lambda e: e["age"]), ("sell", lambda e: e["sell"]), ("vsol", lambda e: e["vsol"]), ("b20", lambda e: e["b20"]), ("s20", lambda e: e["s20"]),
                  ("dd", lambda e: e["dd"]), ("pb", lambda e: e["pb"]), ("nb", lambda e: e["nb"]), ("insider", lambda e: 1.0 if e["ins"] else 0.0)):
        cmp(nm, f)
    sel = collections.Counter(e["seller"] for e in hit).most_common(8); seln = collections.Counter(e["seller"] for e in miss)
    print("  top sellers it backran (backran / not):", [(s, n, seln.get(s, 0)) for s, n in sel])
    # first big sell in the launch vs later ones
    print("  share backran by age band:", [(lo, round(sum(1 for e in EV if lo <= e['age'] < hi and e['hit']) / max(1, sum(1 for e in EV if lo <= e['age'] < hi)), 2)) for lo, hi in ((1, 3), (3, 6), (6, 10), (10, 20), (20, 40), (40, 61))])
    rr = [(x["sell_sol"] / x["buy_sol"]) for x in RT if x["buy_sol"] > 0 and x["tok_b"] == x["tok_s"]]
    print(f"  round trips {len(RT)} (full exits {len(rr)}): median sell/buy SOL {statistics.median(rr):.3f}, mean {statistics.mean(rr):.3f}, median slots {statistics.median(x['slots'] for x in RT)}")
