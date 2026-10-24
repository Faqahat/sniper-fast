#!/usr/bin/env python3
# Strategy lab summary: for each pick list x landing x variant x exit -> total SOL under TODAY's costs (2% buy overhead,
# 0.005 per failed guarded buy) and PRO costs (0.6% overhead like CWiNFA, 0.003 per failed buy: tips / Jito copies
# cost nothing when the tx fails, only the priority fee), fills, median per fill, win rate, total without the best 5,
# and first/second half. Ranked by the strictest number: min(pro-cost total with pro buys after us removed, both halves).
# usage: python3 -I lab_sum.py <file1_become_*.json> ...   (env EXITS, LANDS)
import sys, os, json, statistics
EXITS = os.environ.get("EXITS", "t5,t8,t10").split(","); LANDS = os.environ.get("LANDS", "75,45,30").split(",")
rows = []
for f in sys.argv[1:]:
    R = json.load(open(f)); name = os.path.basename(f).split("_become_")[0]
    t0, t1 = R[0]["bt"], R[-1]["bt"]; mid = (t0 + t1) / 2
    for Lm in LANDS:
        for var in ("slip", "proafter_slip", "nosnip"):
            v = [(r["bt"], r[Lm][var], r.get("B", 0.5)) for r in R if r.get(Lm, {}).get(var)]
            if not v: continue
            fl = [(bt, x) for bt, x, _ in v if x["fill"]]; nf = len(v) - len(fl); nf1 = sum(1 for bt, x, _ in v if not x["fill"] and bt < mid)
            for ex in EXITS:
                if not fl or ex not in fl[0][1]["pnl"]: continue
                p = sorted(x["pnl"][ex] for _, x in fl)
                cur = sum(p) - 0.005 * nf; pro = sum(p) + 0.007 * len(p) - 0.003 * nf
                h1 = sum(x["pnl"][ex] + 0.007 for bt, x in fl if bt < mid) - 0.003 * nf1; h2 = pro - h1
                rows.append(dict(list=name, L=Lm, var=var, ex=ex, fills=len(fl), att=len(v), cur=cur, pro=pro, med=statistics.median(p), win=sum(1 for x in p if x > 0) / len(p),
                                 wo5=pro - sum(p[-5:]) - 0.035, h1=h1, h2=h2, hrs=(t1 - t0) / 3600))
json.dump(rows, open("/home/moiz/sniper/ops/overnight/core/lab_sum.json", "w"))
key = {}
for r in rows:
    if r["var"] == "proafter_slip": key[(r["list"], r["L"], r["ex"])] = min(r["pro"], r["h1"], r["h2"])
print("per list / landing / exit: TODAY-cost total | PRO-cost total [median, win, w/o top5, halves]  — for slip | pro buys after us removed | all sniper buys after us removed")
for (lst, Lm, ex), sc in sorted(key.items(), key=lambda kv: -kv[1])[:40]:
    cells = []
    for var in ("slip", "proafter_slip", "nosnip"):
        r = next(x for x in rows if x["list"] == lst and x["L"] == Lm and x["ex"] == ex and x["var"] == var)
        cells.append(f"{r['cur']:+5.2f}|{r['pro']:+5.2f} [{r['med']:+.3f} {r['win']:.0%} {r['wo5']:+5.2f} {r['h1']:+.1f}/{r['h2']:+.1f}]")
    r0 = next(x for x in rows if x["list"] == lst and x["L"] == Lm and x["ex"] == ex and x["var"] == "slip")
    print(f"{lst:10s} L{Lm} {ex:4s} fills {r0['fills']:3d}/{r0['att']:3d} ({r0['hrs']:.1f} h) | " + " | ".join(cells))
