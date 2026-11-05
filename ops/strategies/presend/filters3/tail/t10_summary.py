#!/usr/bin/env python3
"""TAIL t10: DEV / VAL totals per guard from the frozen scorer's per-run JSON (score/r37..r41, r42a = DEV; r42b = VAL)."""
import json
T = "/home/moiz/sniper-data/filters3/tail/score"
SETS = {"DEV": ["r37", "r38", "r39", "r40", "r41", "r42a"], "VAL": ["r42b"]}
G = ["G1_CREATOR", "G2_CONC", "G3_FRESH", "G4_BREAKER", "UNION", "REC"]
out = {}
for st, runs in SETS.items():
    J = {r: json.load(open(f"{T}/{r}.json")) for r in runs}
    rows = [x for r in runs for x in J[r]["rows"]]
    hrs = sum(J[r]["summary"]["hours"] for r in runs)
    base = [x["pnl"] for x in rows]; bs = sorted(base)
    wr = lambda v: 100 * sum(1 for x in v if x > 0) / len(v) if v else 0
    print(f"\n{st}: {len(runs)} run parts, {hrs:.1f} h, trades {len(rows)}, realized {sum(base):+.3f} SOL ({sum(base)/hrs*24:+.2f}/day), win {wr(base):.0f}%, w/o top 5 trades {sum(bs[:-5]):+.3f}")
    out[st] = {"hours": hrs, "trades": len(rows), "base": sum(base), "base_day": sum(base) / hrs * 24, "base_wr": wr(base), "base_wo_top5": sum(bs[:-5]), "guards": {}}
    for g in G:
        b = [x["pnl"] for x in rows if g in x["g"]]; s = sorted(b)
        kept = [x["pnl"] for x in rows if g not in x["g"]]; ks = sorted(kept)
        per = {r: round(-sum(x["pnl"] for x in J[r]["rows"] if g in x["g"]), 3) for r in runs}
        nper = {r: sum(1 for x in J[r]["rows"] if g in x["g"]) for r in runs}
        o = {"blocked": len(b), "winners": [sum(1 for x in b if x > 0), round(sum(x for x in b if x > 0), 3)], "losers": [sum(1 for x in b if x <= 0), round(sum(x for x in b if x <= 0), 3)],
             "big_losses": [sum(1 for x in b if x < -0.04), round(sum(x for x in b if x < -0.04), 3)], "saved": round(-sum(b), 3), "saved_day": round(-sum(b) / hrs * 24, 3),
             "saved_wo_its_top5": round(-sum(s[5:]), 3), "after": round(sum(kept), 3), "after_day": round(sum(kept) / hrs * 24, 3), "after_wr": round(wr(kept), 1),
             "after_wo_top5_trades": round(sum(ks[:-5]), 3), "per_run_saved": per, "per_run_blocked": nper}
        out[st]["guards"][g] = o
        print(f"  {g:11s} blk {o['blocked']:3d} | winners {o['winners'][0]} {o['winners'][1]:+.3f} | losers {o['losers'][0]} {o['losers'][1]:+.3f} (big {o['big_losses'][0]} {o['big_losses'][1]:+.3f}) | saved {o['saved']:+.3f} ({o['saved_day']:+.2f}/day) w/o its 5 best {o['saved_wo_its_top5']:+.3f}"
              f" | after {o['after']:+.3f} ({o['after_day']:+.2f}/day) win {o['after_wr']:.0f}% w/o top5 {o['after_wo_top5_trades']:+.3f} | " + " ".join(f"{r}:{nper[r]}/{per[r]:+.2f}" for r in runs if nper[r]))
json.dump(out, open("/home/moiz/sniper-data/filters3/tail/summary.json", "w"), indent=1)
