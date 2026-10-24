#!/usr/bin/env python3
# How does ARu4n5mF trade? Per position: its buys and sells (slot after create, SOL, price vs its first buy, price vs post-bundle),
# what preceded its first buy, and PnL. Biggest positions first.
import sys, os, json, gzip, glob, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry"); os.environ["RP_REPAIR"] = "0"
import rp
from multiprocessing import Pool
WP = sys.argv[1] if len(sys.argv) > 1 else "ARu4n5mF"
rows = {}; U = None
for f in glob.glob("/home/moiz/sniper/ops/overnight/census/parts/*.jsonl.gz"):
    for l in gzip.open(f, "rt"):
        if l[2:2 + len(WP)] == WP: r = json.loads(l); rows[r[1]] = r; U = r[0]
L = rp.load_launches()
byb = collections.defaultdict(set)
for m in rows: byb[(L[m]["run"], rp.bucket(m))].add(m)
def work(key):
    run, b = key; out = []
    for m, tr in rp.read_bucket(run, b, byb[key]).items():
        c = L[m]; S = c["slot"]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; pb = ge["vsol"] / ge["vtok"]
        mine = [(k, t) for k, t in enumerate(tr) if t["user"] == U]
        if not mine: continue
        p0 = None; seq = []
        for k, t in mine:
            p = (t["vsol"] - t["sol"]) / (t["vtok"] + t["tok"]) if t["buy"] else (t["vsol"] + t["sol"]) / (t["vtok"] - t["tok"])
            if p0 is None: p0 = p
            seq.append(("B" if t["buy"] else "S", t["s"] - S, round(t["sol"] / 1e9, 3), round(p / p0, 3), round(p / pb, 2)))
        k0 = mine[0][0]
        nb_before = sum(1 for t in tr[:k0] if t["buy"]); ub_before = len({t["user"] for t in tr[:k0] if t["buy"]})
        vs = tr[k0 - 1]["vsol"] / 1e9 if k0 > 0 else 30
        out.append(dict(m=m, name=c.get("name"), run=run, pnl=rows[m][11], spent=rows[m][7], nbuys=sum(1 for x in seq if x[0] == "B"), seq=seq[:12],
                        nb_before=nb_before, ub_before=ub_before, vsol_entry=round(vs, 1), age_entry=seq[0][1], px_vs_bundle=seq[0][4]))
    return out
if __name__ == "__main__":
    res = []
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(byb)): res += o
    json.dump(res, open(f"/home/moiz/sniper/ops/overnight/census/pos_{WP}.json", "w"))
    print(U, "positions", len(res), "pnl", round(sum(r["pnl"] for r in res), 2))
    for r in sorted(res, key=lambda r: -r["spent"])[:8]:
        print(f"\n{r['name']} ({r['m'][:8]}, {r['run']}) pnl {r['pnl']:+.2f} spent {r['spent']:.2f} buys {r['nbuys']} | entry age {r['age_entry']} slots, {r['ub_before']} buyers before, vsol {r['vsol_entry']}, px/bundle {r['px_vs_bundle']}")
        print("   ", r["seq"])
    def band(title, key, edges):
        o = []
        for lo, hi in zip(edges[:-1], edges[1:]):
            x = [r for r in res if lo <= key(r) < hi]
            if x: o.append(f"[{lo},{hi}) n{len(x)} {sum(r['pnl'] for r in x):+.1f} w{sum(1 for r in x if r['pnl'] > 0) / len(x):.0%}")
        print(f"  {title}: " + " | ".join(o))
    print()
    band("number of buys", lambda r: r["nbuys"], [1, 2, 3, 5, 10, 1000])
    band("vsol at entry", lambda r: r["vsol_entry"], [0, 32, 35, 40, 50, 60, 80, 120])
    band("price at entry / post-bundle", lambda r: r["px_vs_bundle"], [0, 0.8, 1, 1.5, 2, 3, 5, 100])
    band("buyers before entry", lambda r: r["ub_before"], [0, 5, 10, 20, 50, 100, 10 ** 6])
