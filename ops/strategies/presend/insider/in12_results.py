#!/usr/bin/env python3
"""INSIDER step 12: RESULTS.json / RESULTS.txt (data folder)."""
import json, pickle, glob, collections
import numpy as np
D = "/home/it/sniper-data/insider"
T = json.load(open(f"{D}/tables_all.json"))
E = json.load(open(f"{D}/explain_r37.json"))
# census rebuild: all 4 r37 parts vs the 3 parts the first count used (part 2 = multiarm/raw/r37.obs.jsonl.3)
cen = {}
for run in ("r36", "r37", "r38", "r39"):
    R = pickle.load(open(f"{D}/cen_{run}.pkl", "rb"))
    c = {}
    for cl in ("creator", "insider", "first_buy", "laddered", "repeat"):
        f = [r["paper"] for r in R if r["class"] == cl and r["paper"] is not None]
        c[cl] = {"fills": len(f), "paper_sol": round(sum(f) / 1e3, 2)}
    ins10 = [r["paper"] for r in R if r["class"] == "insider" and r["pct"] >= 10 and r["age"] == 0 and r["paper"] is not None]
    c["insider_ge10_age0"] = {"fills": len(ins10), "paper_sol": round(sum(ins10) / 1e3, 2)}
    cen[run] = c
# base calibration: replay T2 / R0 cash vs live realized (x_*.pkl meta)
cal = {}
for run, rd, xp in (("r37", f"{D}/runs/r37", "/home/it/sniper-data/multiarm/x_r37.pkl"), ("r38", f"{D}/runs/r38", "/home/it/sniper-data/multiarm/x_r38.pkl"),
                    ("r36", f"{D}/runs/r36", f"{D}/x_r36.pkl"), ("r39", f"{D}/runs/r39", f"{D}/x_r39.pkl")):
    reps = [pickle.load(open(f, "rb")) for f in sorted(glob.glob(f"{rd}/BASE__*.pkl"))]
    t2 = np.mean([sum(r["cash"] for r in d["rows"] if r["kind"] == "t2") for d in reps]); re = np.mean([sum(r["cash"] for r in d["rows"] if r["kind"] == "rearm") for d in reps])
    t2f = np.mean([sum(r["filled"] for r in d["rows"] if r["kind"] == "t2") for d in reps])
    X = pickle.load(open(xp, "rb"))
    live = collections.defaultdict(float); lf = collections.Counter()
    for W in X["wins"]:
        if W.get("real"): live[W["kind"]] += sum(x["pnl"] or 0 for x in W["real"]) / 1e9 if abs(sum(x["pnl"] or 0 for x in W["real"])) > 1e3 else sum(x["pnl"] or 0 for x in W["real"])
        lf[W["kind"]] += 1 if W.get("fills") else 0
    cal[run] = {"hours": reps[0]["meta"]["hours"], "replay_t2_sol": round(float(t2), 3), "replay_t2_fills": round(float(t2f), 1), "replay_rearm_sol": round(float(re), 3),
                "live_realized": {k: round(v, 3) for k, v in live.items()}, "live_fills": dict(lf)}
keys = ["INS_e1_X15_W15", "INS_e1_X15_W10", "INS_e1_X15_W20", "INS_x_X15_W10_solo", "INS_x_X15_W10", "INS_x_X10_W10", "INS_x_X10_W20", "INS_e0_X10_W10", "INS_x_X8_W10", "INS_x_X6_W10"]
slim = {n: {r: {k: v for k, v in T[n][r].items() if not k.startswith("_")} for r in T[n]} for n in T}
hourly = {n: {r: {"pkt": T[n][r]["_pkt"], "net_sol": [round(x, 3) for x in T[n][r]["_hourly"]]} for r in ("r37", "r36", "r38", "r39")} for n in keys}
qual = [n for n in T if T[n]["r37"]["wo5_day"] > 0 and T[n]["r37"]["added_cut_day"] > 0]
out = {"verdict": "FAIL", "pick_qualifiers_on_r37": qual, "census": cen, "base_calibration": cal, "tables": slim, "hourly_key_variants": hourly, "explain_r37": E,
       "rebuy_r37_ge10": {"next_tx_rebuys_above_0.88": [46, 7.08], "rebought_later_same_block": [88, 26.67], "still_down_at_block_end": [108, -1.02]},
       "rebuy_r36_ge10": {"next_tx_rebuys_above_0.88": [28, 3.40], "rebought_later_same_block": [30, 8.65], "still_down_at_block_end": [45, -0.95]},
       "rebuy_r37_ge6": {"next_tx_rebuys_above_0.88": [142, 14.39], "rebought_later_same_block": [136, 30.68], "still_down_at_block_end": [369, -17.31]}}
json.dump(out, open(f"{D}/RESULTS.json", "w"), indent=1)
L = []
L.append("INSIDER dumps (observatory census class 'insider'): PROVE OR KILL -- verdict FAIL (2026-10-30 PKT)")
L.append("PICK r37 (17.7 h), TEST r36 (4.1 h) + r38 (1.5 h) + r39-so-far (1.0 h); joint try-level replay (multiarm ma4_sim) with T2 + R0 as live; 4 reps")
L.append(f"r37 qualifiers (w/o top5 > 0 and -20% > 0): {qual or 'NONE'}")
L.append("added SOL/day vs live T2+R0 | r37: slip / -20% / w/o top5 | TEST: slip / -20% / w/o top5 / CI90 | ins fills/day r37")
for n in keys:
    a = T[n]["r37"]; t = T[n]["TEST"]
    L.append(f"  {n:20s} {a['added_day']:+6.2f} {a['added_cut_day']:+6.2f} {a['wo5_day']:+6.2f} | {t['added_day']:+6.2f} {t['added_cut_day']:+6.2f} {t['wo5_day']:+6.2f} {t['ci90_day']} | {a['ins_fills_day']}")
L.append("census rebuild (paper, zero latency, no costs): " + json.dumps({r: c["insider"] for r, c in cen.items()}))
L.append("census insider >=10% age0: " + json.dumps({r: c["insider_ge10_age0"] for r, c in cen.items()}))
L.append("same-block rebuy (r37, insider >=10% paper fills): next tx re-buys above 0.88x 46 (+7.08 SOL paper); later same block 88 (+26.67); stays down 108 (-1.02)")
L.append("base calibration (replay vs live): " + json.dumps(cal))
open(f"{D}/RESULTS.txt", "w").write("\n".join(L) + "\n")
print("\n".join(L))
