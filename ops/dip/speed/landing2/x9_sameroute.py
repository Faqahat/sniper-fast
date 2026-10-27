#!/usr/bin/env python3
# Same route, same leader client: our landed copy vs the pros' landed copy (same-slot landings, dumps in Q1-Q3 of their block).
# If the same relay lands later for us than for a pro, the gap is upstream of the relay (seeing the dump + deciding + our hop to it).
import sys, json, collections, statistics as st
sys.path.insert(0, "/home/moiz/sniper/ops/dip/speed/landing2")
import lib2
rows = json.load(open(f"{lib2.D}/pro_rows_1.0_0.04.json"))
WAL = json.load(open(f"{lib2.D}/wallets.json"))
FIRES = json.load(open(f"{lib2.D}/our_fires.json")); fd = {f["dump_sig"] for f in FIRES}
OURS = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE": "OURS-FRA", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR": "OURS-AMS"}
def who(w):
    if w in OURS: return "OURS"
    g = WAL[w]["grp"]
    return "PRO-" + WAL[w]["name"][:8] if g in ("pro", "hicu") else None
def r1(r):
    s = r["svc"]
    return s.split("+")[0] if "+" not in s else "multi"
med = lambda v: round(st.median(v), 1) if v else None
def pc(v, p): v = sorted(v); return round(v[min(len(v)-1, int(p*len(v)))], 1) if v else None
G = collections.defaultdict(list)
for r in rows:
    if r["w"] in OURS and r["dump"] not in fd: continue
    if r["ds"] != 0 or r["q"] > 2: continue
    k = who(r["w"])
    if not k: continue
    G[(r["cl"], r1(r), "OURS" if k == "OURS" else "PROS")].append(r["ms"])
    if k != "OURS": G[(r["cl"], r1(r), k)].append(r["ms"])
print("same-slot landings on dumps in Q1-Q3; median ms (p25) (n) by leader client x landed route; OURS vs all pros+hicu pooled; best single pro")
for cl in ("Jito-own", "Jito-relayer", "BAM", "Harmonic", "Firedancer"):
    print(f"== {cl}")
    routes = sorted({k[1] for k in G if k[0] == cl}, key=lambda s: -len(G[(cl, s, "PROS")]))
    for rt in routes:
        o = G.get((cl, rt, "OURS"), []); p = G.get((cl, rt, "PROS"), [])
        if len(p) < 20 and len(o) < 5: continue
        best = sorted(((med(G[k]), k[2], len(G[k])) for k in G if k[0] == cl and k[1] == rt and k[2].startswith("PRO-") and len(G[k]) >= 15))
        print(f"   {rt:13s} OURS {str(med(o)):>6s} ({str(pc(o,.25)):>5s}) n={len(o):3d} | PROS {str(med(p)):>6s} ({str(pc(p,.25)):>5s}) n={len(p):5d} | best pro {best[0] if best else '-'}")
