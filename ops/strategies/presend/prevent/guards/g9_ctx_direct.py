#!/usr/bin/env python3
"""GUARDS step 9 [MEASURED live fills, DIRECT only - no replacement fills]: the context-limit lead d15_if_h1 on ALL 20 live runs:
a T2 fill is removed if at its signing at least one wallet other than the whale held >= 6% of supply AND the fill's depth (price drop from
the signing price to the price just before our buy) was < 15%. Gain = minus the realized P&L (scaled to 0.696) of the removed fills.
usage: g9_ctx_direct.py"""
import pickle, collections, json
OUT = "/home/it/sniper-data/prevent/guards"
R = pickle.load(open(f"{OUT}/feats.pkl", "rb"))
ORDER = ["F21", "F22", "F23", "F24", "F26", "F27", "F28", "A16", "A17", "A19", "A20", "A24", "A25", "A26", "A27", "A34", "A35", "A36", "A37", "A38"]
FIXC = 0.003524
def sc(o): return (o["pnl"] + FIXC) * 0.696 / (o["spend"] / 1e9) - FIXC
res = {}
lines = ["d15_if_h1 DIRECT (removed = T2 fills with an other >= 6% holder at signing and depth < 15%; d18 = depth < 18%)",
         f"{'run':4s} {'T2 fills':>8s} | {'d15 removed':>11s} {'gain@0.696':>10s} | {'d18 removed':>11s} {'gain@0.696':>10s}"]
for run in ORDER:
    v = [o for o in R if o["run"] == run and o["kind"] == "t2"]
    row = {}
    for D in (0.15, 0.18):
        rm = [o for o in v if any(u != o["whale"] for u in o["H6_S"]) and o["p_pre"] and o["p_sign"] and (1 - o["p_pre"] / o["p_sign"]) < D]
        row[D] = (len(rm), -sum(sc(o) for o in rm))
    res[run] = {"t2_fills": len(v), "d15": row[0.15], "d18": row[0.18]}
    lines.append(f"{run:4s} {len(v):8d} | {row[0.15][0]:11d} {row[0.15][1]:+10.3f} | {row[0.18][0]:11d} {row[0.18][1]:+10.3f}")
pk = [r for r in ORDER if r not in ("A37", "A38")]
for D in ("d15", "d18"):
    g = sum(res[r][D][1] for r in pk); p = sum(1 for r in pk if res[r][D][1] > 1e-9); m = sum(1 for r in pk if res[r][D][1] < -1e-9)
    lines.append(f"{D}: PICK gain {g:+.3f} (runs +{p}/-{m}), r37 {res['A37'][D][1]:+.3f}, r38 {res['A38'][D][1]:+.3f}")
open(f"{OUT}/ctx_direct.txt", "w").write("\n".join(lines) + "\n"); json.dump(res, open(f"{OUT}/ctx_direct.json", "w"), indent=1)
print("\n".join(lines))
