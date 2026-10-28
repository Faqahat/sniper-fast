#!/usr/bin/env python3
"""Q1: landing by leader location (leader_geo.json IP geo, epoch-1063 measurement; MEASURED geo, slightly stale). His tiered buys
(T -> buy) and [t7] dump buys vs our pre-send fills. Out: x13.txt"""
import sys, json, pickle, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/exec")
import numpy as np, xlib as X
G = {r["pk"]: r.get("cc") for r in json.load(open("/home/moiz/sniper-data/leader_geo.json"))["rows"]}
EU = set("DE NL GB IE FR BE CH AT PL LT CZ FI SE IT ES LU DK NO RO BG UA HU PT LV EE".split())
def area(slot):
    ld, _ = X.leader(slot); cc = G.get(ld)
    if cc is None: return "?"
    if cc == "DE": return "DE"
    if cc == "NL": return "NL"
    if cc in EU: return "EU-other"
    if cc in ("US", "CA"): return "N.America"
    return "Asia/other"
r1 = [r for r in pickle.load(open(f"{X.X}/x1.pkl", "rb")) if r["day"] == "D1"]
o = pickle.load(open(f"{X.X}/x2.pkl", "rb"))["rows"]
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
P("leader area share of his D1 buys:", dict(collections.Counter(area(r["s"]) for r in r1)))
P("HIS size-code trigger -> buy (D1), by leader area of his slot:")
for a in ("DE", "NL", "EU-other", "N.America", "Asia/other", "?"):
    v = [r for r in r1 if "ms" in r and area(r["s"]) == a]
    if len(v) >= 10: P(f"  {a:11} n={len(v):4} ms p50 {X.med([r['ms'] for r in v]):4.0f}  same-slot {100*np.mean([r['gap']==0 for r in v]):3.0f}%")
P("HIS [t7 dump def] by leader area:")
D = [r for r in r1 if "pms" in r and not r["pbuy"] and r["psol"] >= 0.5 and r["pgap"] <= 2]
for a in ("DE", "NL", "EU-other", "N.America", "Asia/other"):
    v = [r for r in D if area(r["s"]) == a]
    if len(v) >= 5: P(f"  {a:11} n={len(v):4} ms p50 {X.med([r['pms'] for r in v]):4.0f}  same-slot {100*np.mean([r['pgap']==0 for r in v]):3.0f}%")
P("OUR pre-send fills [t7 dump def] by leader area (FRA r27/r28 + AMS r28):")
Do = [r for r in o if not r["pbuy"] and r["psol"] >= 0.5 and r["pgap"] <= 2]
P("  leader area share of our fills:", dict(collections.Counter(area(r["s"]) for r in Do)))
for a in ("DE", "NL", "EU-other", "N.America", "Asia/other"):
    v = [r for r in Do if area(r["s"]) == a]
    if len(v) >= 5: P(f"  {a:11} n={len(v):4} ms p50 {X.med([r['pms'] for r in v]):4.0f}  same-slot {100*np.mean([r['pgap']==0 for r in v]):3.0f}%")
open(f"{X.X}/x13.txt", "w").write("\n".join(out) + "\n")
