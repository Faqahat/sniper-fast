#!/usr/bin/env python3
"""WHO step 10: RESULTS.json / RESULTS.txt -- per-run tables of the leads, r38 six-loss flags, counts."""
import json, sys
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/prevent/who")
from w6_score import ALL_LIVE, SIX
from w5_rules import PAPER_RUNS
D = "/home/moiz/sniper-data/prevent/who"
A = json.load(open(f"{D}/score.json")); B = json.load(open(f"{D}/score_rules_posthoc.json"))
R = dict(A["rules"]); R.update(B["rules"])
post = set(B["rules"])
leads = ["E1 bundle sum>=20.0", "G-cr fair-list creator m2 S0.05", "G-cr fair-list creator m3 S0.05", "G-cr fair-list creator m2 S0.2",
         "A X1.0 n2 L0.05 Y3.0", "G fair-list m2 S0.1", "C2 trig past fills<0 n>=2", "D1 creator holds>=6.0", "C1 whale dumps24h>=5", "B P6 K5 N6 Y3.0 excl-trig", "H cascade Y6.0 K5 excl-trig", "F bot holds>=3.0", "E3 holder>=3 same first slot as trigger"]
L = []
L.append("PER-RUN SAVING @0.696 SOL (+ = the rule would have saved SOL; live runs then PAPER shadow-only runs, row c)")
L.append("run     " + " ".join(f"{k[:14]:>14s}" for k in leads))
for r in ALL_LIVE: L.append(f"{r:7s} " + " ".join(f"{R[k]['per_run'][r]:+14.3f}" for k in leads))
L.append("PICK    " + " ".join(f"{R[k]['pick']:+14.3f}" for k in leads))
L.append("TESTr37 " + " ".join(f"{R[k]['test']:+14.3f}" for k in leads))
L.append("r38     " + " ".join(f"{R[k]['r38']:+14.3f}" for k in leads))
for r in PAPER_RUNS: L.append(f"{r:6s}P " + " ".join(f"{R[k]['per_paper'][r]:+14.3f}" for k in leads))
L.append("PAPER   " + " ".join(f"{R[k]['paper']:+14.3f}" for k in leads))
L.append("help/hurt PICK runs " + " | ".join(f"{k[:14]} {R[k]['help']}/{R[k]['hurt']}" for k in leads))
L.append("")
names = [f"{m[:8]} {k}" for _, m, k in SIX] + ["5cMetpCp t2"]
L.append("r38 SIX LOSSES (+5cMetpCp): rules that would have skipped each (verdict) ; pre-registered 145 + post-hoc 35")
for i, nm in enumerate(names):
    fl = [k for k, o in R.items() if (o["six"][i] if i < len(SIX) else (o["five_c"] or [False])[0])]
    good = [k for k in fl if R[k]["verdict"] in ("PASS", "LEAD")]
    L.append(f"  {nm:16s} skipped by {len(fl):3d} rules; of them PASS/LEAD: {good[:6]}")
txt = "\n".join(L)
print(txt)
open(f"{D}/RESULTS.txt", "w").write(open(f"{D}/taxonomy.txt").read() + "\n\n" + txt + "\n\n" + open(f"{D}/gcr.txt").read())
json.dump({"n_rules_prereg": len(A["rules"]), "n_rules_posthoc": len(B["rules"]), "finalists_prereg": A["finalists"],
           "verdicts": {k: {"verdict": o["verdict"] + (" (post-hoc)" if k in post else ""), "pick": o["pick"], "test": o["test"], "r38": o["r38"], "paper": o["paper"],
                            "ci90": o["ci90"], "wo_top1": o["wo_top1"], "wo_top5": o["wo_top5"], "help": o["help"], "hurt": o["hurt"],
                            "skip_win_sol": o["skip_win_sol"], "skip_loss_sol": o["skip_loss_sol"], "skip_fill_share": o["skip_fill_share"],
                            "per_run": o["per_run"], "per_paper": o["per_paper"], "six": o["six"]} for k, o in R.items()}},
          open(f"{D}/RESULTS.json", "w"), indent=1)
