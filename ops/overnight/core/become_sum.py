#!/usr/bin/env python3
# Compact robustness table for become_eval.py outputs: per pick list, landing, variant and exit:
# total SOL (incl. -0.005 per failed guarded buy), fills, per-fill median, win rate, total without the best 5 fills,
# first half / second half by time, and fills with no outside buy after us.
# usage: python3 -I become_sum.py <list>_become_B0.5.json [...]   (env EXITS="t5,t8,t10,t15", VARS="slip,proafter_slip,nosnip")
import sys, json, os, statistics
EXITS = os.environ.get("EXITS", "eos1,t5,t8,t10,t15").split(","); VARS = os.environ.get("VARS", "slip,proafter_slip,nopro_slip,nosnip").split(",")
for f in sys.argv[1:]:
    R = json.load(open(f)); name = os.path.basename(f).replace("_become_B0.5.json", "")
    t0, t1 = R[0]["bt"], R[-1]["bt"]; mid = t0 + (t1 - t0) / 2; hrs = (t1 - t0) / 3600
    print(f"\n=== {name}: {len(R)} picks over {hrs:.1f} h")
    for Lm in ("75", "45"):
        for var in VARS:
            v = [(r["bt"], r[Lm][var]) for r in R if r.get(Lm, {}).get(var) is not None]
            fills = [(bt, x) for bt, x in v if x["fill"]]; nf = len(v) - len(fills)
            cells = []
            for ex in EXITS:
                p = sorted(x["pnl"][ex] for _, x in fills)
                tot = sum(p) - 0.005 * nf; top5 = sum(p[-5:]) if len(p) >= 5 else sum(p)
                h1 = sum(x["pnl"][ex] for bt, x in fills if bt < mid) - 0.005 * sum(1 for bt, x in v if not x["fill"] and bt < mid)
                cells.append(f"{ex} {tot:+5.2f} [med {statistics.median(p) if p else 0:+.3f} win {sum(1 for x in p if x > 0)}/{len(p)} -top5 {tot - top5:+5.2f} h {h1:+.1f}/{tot - h1:+.1f}]")
            flat = sum(1 for _, x in fills if x["nb"] == 0)
            print(f"  L{Lm} {var:13s} fills {len(fills):3d}/{len(v):3d} flat {flat:2d} | " + " | ".join(cells))
