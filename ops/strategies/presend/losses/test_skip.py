"""Arm-time skip rules: skipping a fill removes its realized pnl (fail fees of skipped arms not credited: conservative)."""
import random
from feat import *
R = {run: [dict(feats(r), mint=r["mint"]) for r in load(run)] for run in RUNS}
def boot(v, n=4000):
    random.seed(7); b = sorted(sum(random.choice(v) for _ in v) for _ in range(n)); return b[int(.05 * n)], b[int(.95 * n)]
RULES = {
  "whale_buy>=5": lambda x: x["trig_sol"] >= 5, "whale_buy>=5.5": lambda x: x["trig_sol"] >= 5.5,
  "whale_buy>=6": lambda x: x["trig_sol"] >= 6, "whale_buy>=6.5": lambda x: x["trig_sol"] >= 6.5,
  "whale_buy in [6,8)": lambda x: 6 <= x["trig_sol"] < 8,
  "age<2 slots": lambda x: x["trig_age"] < 2, "age<3": lambda x: x["trig_age"] < 3, "age<5": lambda x: x["trig_age"] < 5,
  "q0 (a) true": lambda x: bool(x["q"] and x["q"][0]),
  "buy>=6 or age<2": lambda x: x["trig_sol"] >= 6 or x["trig_age"] < 2,
  "buy>=6 or age<3": lambda x: x["trig_sol"] >= 6 or x["trig_age"] < 3,
  "trig_vsol>=45": lambda x: x["trig_vsol"] >= 45,
}
def run_rule(fn):
    out = {}
    for run in RUNS:
        sk = [x for x in R[run] if x["trig_sol"] is not None and fn(x)]
        out[run] = dict(n=len(sk), saved=-sum(x["pnl"] for x in sk if x["pnl"] < 0), lost=sum(x["pnl"] for x in sk if x["pnl"] >= 0),
                        nw=sum(1 for x in sk if x["pnl"] >= 0), d=[(-x["pnl"] if x["trig_sol"] is not None and fn(x) else 0.0) for x in R[run]])
    return out
if __name__ == "__main__":
    print(f"{'rule':18s} " + " ".join(f"{r:>28s}" for r in RUNS) + "   train net  90%CI  -top5 | r36 | all4 CI")
    for name, fn in RULES.items():
        o = run_rule(fn); tr = [v for r in RUNS[:3] for v in o[r]["d"]]; al = tr + o["r36"]["d"]
        lo, hi = boot(tr); s = sorted(tr, reverse=True); alo, ahi = boot(al)
        print(f"{name:18s} " + " ".join(f"n{o[r]['n']:3d}({o[r]['nw']}w) +{o[r]['saved']:.3f}/-{o[r]['lost']:.3f}={o[r]['saved']-o[r]['lost']:+.3f}" for r in RUNS)
              + f"  {sum(tr):+.3f} [{lo:+.3f},{hi:+.3f}] {sum(s[5:]):+.3f} | {sum(o['r36']['d']):+.3f} | {sum(al):+.3f} [{alo:+.3f},{ahi:+.3f}] -top5 {sum(sorted(al,reverse=True)[5:]):+.3f}")
