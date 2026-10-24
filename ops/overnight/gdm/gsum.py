#!/usr/bin/env python3
# GDM summary of become_eval outputs for pick SUBSETS over a common time window (same metrics as core/lab_sum.py):
# total SOL at TODAY's costs (2% overhead, -0.005 per failed guarded buy) and PRO costs (+0.007 per 0.5 SOL fill,
# -0.003 per failed buy), fills / attempts, median per fill, win rate, PRO-cost total without the best 5 fills, PRO-cost
# halves (common time midpoint of the window).
# usage: python3 -I gsum.py <become_output.json> <t0> <t1> <name=picks.json> ...   (env EXITS=t8,t10 LANDS=75,45,30)
import sys, os, json, statistics
EXITS = os.environ.get("EXITS", "t8,t10").split(","); LANDS = os.environ.get("LANDS", "75,45,30").split(",")
VARS = os.environ.get("VARS", "slip,proafter_slip,nosnip").split(",")
def summarize(R, sub, t0, t1):
    mid = (t0 + t1) / 2; rows = []
    R = [r for r in R if r["m"] in sub and t0 <= r["bt"] <= t1]
    for Lm in LANDS:
        for var in VARS:
            v = [(r["bt"], r[Lm][var]) for r in R if r.get(Lm, {}).get(var)]
            fl = [(bt, x) for bt, x in v if x["fill"]]; nf = len(v) - len(fl); nf1 = sum(1 for bt, x in v if not x["fill"] and bt < mid)
            for ex in EXITS:
                p = sorted(x["pnl"][ex] for _, x in fl)
                cur = sum(p) - 0.005 * nf; pro = sum(p) + 0.007 * len(p) - 0.003 * nf
                h1 = sum(x["pnl"][ex] + 0.007 for bt, x in fl if bt < mid) - 0.003 * nf1
                rows.append(dict(L=Lm, var=var, ex=ex, fills=len(p), att=len(v), cur=round(cur, 3), pro=round(pro, 3), med=round(statistics.median(p), 4) if p else 0.0,
                                 win=round(sum(1 for x in p if x > 0) / len(p), 3) if p else 0.0, wo5=round(pro - sum(p[-5:]) - 0.007 * min(5, len(p)), 3),
                                 h1=round(h1, 3), h2=round(pro - h1, 3)))
    return rows
if __name__ == "__main__":
    R = [r for fn in sys.argv[1].split(",") for r in json.load(open(fn))]; t0, t1 = float(sys.argv[2]), float(sys.argv[3]); out = {}
    for a in sys.argv[4:]:
        nm, f = a.split("=", 1); sub = set(json.load(open(f))); out[nm] = summarize(R, sub, t0, t1)
    for nm, rows in out.items():
        print(f"\n== {nm}")
        for r in rows:
            print(f"  L{r['L']:>2s} {r['var']:13s} {r['ex']:3s} fills {r['fills']:3d}/{r['att']:3d} | today {r['cur']:+6.2f} | PRO {r['pro']:+6.2f} | med {r['med']:+.4f} win {r['win']:.0%} | w/o top5 {r['wo5']:+6.2f} | halves {r['h1']:+5.2f} / {r['h2']:+5.2f}")
    if os.environ.get("JSON_OUT"): json.dump(out, open(os.environ["JSON_OUT"], "w"), indent=0)
