#!/usr/bin/env python3
"""FRONT step 11 (read-only, INFERRED what-ifs on MEASURED inputs): on the paying dumps we ATTEMPTED (pre-send armed / regular fired),
how much front value we would take if our first landing after the dump were t ms after it (we are first iff front buyer #1 landed
later than t; faster buyers stay ahead). Value per capture calibrated like dv8: 0.61 x model - 1.17 mSOL, minus the fill cost
(pre-send 2.01, regular 3.52 mSOL; lim l18), and the fol 0.9 version (10% fewer followers) as the low end.
Also: capture rate by leader region on attempted dumps. Out: sniper-data/haqq_dissect/front/f11.txt"""
import pickle, collections, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/front"
R = pickle.load(open(f"{OUT}/f8_rows.pkl", "rb")); R1 = pickle.load(open(f"{OUT}/f1.pkl", "rb"))
FULL = (2, 3, 4, 5); out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
att = [r for r in R if r["st"][0] in "678" and r["day"] in FULL]
P(f"# What-if: our landing time after the dump on the paying dumps we attempted (D2..D5: {len(att):,} dumps)")
for kind, cf, sel in (("pre-send", 2.01, lambda r: r["st"].startswith("6") or (r["st"].startswith("8") and r["ourbest"][2] == "ps")),
                      ("regular", 3.52, lambda r: r["st"].startswith("7") or (r["st"].startswith("8") and r["ourbest"][2] == "reg"))):
    g = [r for r in att if sel(r)]
    days = sorted(set(r["day"] for r in g)); nd = len(days)
    ms = np.array([r["f1"]["ms"] if not r.get("splus") else 1e9 for r in g]); v = np.array([r["v"] for r in g])
    v9 = np.array([R1[r["i"]]["vf9"] / R1[r["i"]]["vf"] * r["v"] if R1[r["i"]]["vf"] and not np.isnan(R1[r["i"]]["vf9"]) else 0.9 * r["v"] for r in g])
    cur = sum(r["st"].startswith("8") for r in g)
    net = lambda x: 0.61 * x * 1000 - 1.17 - cf
    P(f"\n## {kind}: {len(g):,} attempted paying dumps over {nd} days ({len(g)/nd:.0f}/day); captured now {cur} ({100*cur/len(g):.1f}%); "
      f"front #1 ms after dump p25/p50/p75 {np.percentile(ms[ms<1e8],25):.1f}/{np.median(ms[ms<1e8]):.1f}/{np.percentile(ms[ms<1e8],75):.1f}")
    P("| our landing after the dump | share where we would be first | captures/day | net SOL/day (calibrated, fol 1.0) | fol 0.9 | gain vs now SOL/day |")
    P("|---|---|---|---|---|---|")
    now = sum(net(x) for x, r in zip(v, g) if r["st"].startswith("8")) / 1000 / nd
    for t in (0, 3, 5, 10, 15, 20, 30, 50):
        m = ms > t
        a = sum(net(x) for x in v[m]) / 1000 / nd; b = sum(net(x) for x in v9[m]) / 1000 / nd
        P(f"| {t} ms | {100*m.mean():.0f}% | {m.sum()/nd:.1f} | {a:+.2f} | {b:+.2f} | {a-now:+.2f} |")
    P(f"- now (captured): {now:+.2f} SOL/day calibrated")
# capture rate by region / client on attempted
P("\n## Attempted paying dumps: capture rate and our first landing ms, by leader region and client (D2..D5)")
for key in ("region", "client"):
    P(f"| {key} | attempted | captured | rate | our first landing ms p50 (excl. captured) | front #1 ms p50 |")
    P("|---|---|---|---|---|---|")
    for k in sorted(set(r[key] for r in att), key=lambda k: -sum(r[key] == k for r in att)):
        g = [r for r in att if r[key] == k]
        if len(g) < 10: continue
        c = sum(r["st"].startswith("8") for r in g)
        om = [r["ourbest"][4] for r in g if r["ourbest"] and not r["st"].startswith("8") and r["ourbest"][4] is not None]
        P(f"| {k} | {len(g)} | {c} | {100*c/len(g):.1f}% | {np.median(om) if om else float('nan'):.0f} | {np.median([r['f1']['ms'] for r in g if not r.get('splus')]):.1f} |")
open(f"{OUT}/f11.txt", "w").write("\n".join(out) + "\n")
