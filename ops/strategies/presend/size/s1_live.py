#!/usr/bin/env python3
"""SIZE study step 1 (read-only, offline): parse AMS r26, r27, r28 records with REPLAY_065's live.py (same parser as r24/r25).
Inputs: /home/moiz/sniper-data/presend_size/live/dip_ams_r{26,27,28}.{jsonl,log} (r26/r27 = local copies, r28 = sudo cat 10-27 22:17 PKT,
md5 = server). Writes /home/moiz/sniper-data/presend_size/live.pkl. MEASURED."""
import sys, pickle
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real/r065")
import live as L
L.LIVE = "/home/moiz/sniper-data/presend_size/live"
OUT = "/home/moiz/sniper-data/presend_size/live.pkl"
RUNS = ("r26", "r27", "r28")
if __name__ == "__main__":
    D = {}
    for run in RUNS:
        R = L.load(run); D[run] = R
        F = L.presend_fills(R)
        print(run, "segs", [(s["seg"], s["ps_spend"], s["spend"], s["guard"], s["hold"]) for s in R["segs"]], "start", R["start_bal"])
        print("   pre-send positions", len(F), "multi-fill", sum(1 for x in F if x["n_fills"] > 1), "realized %+.4f" % (sum(x["realized"] or 0 for x in F) / 1e9),
              "log n", len(R["log_ps_real"]), "sum %+.4f" % sum(p for _, _, p in R["log_ps_real"]))
        print("   regular fires", len(R["fires"]), "buy_land", len(R["buy_land"]), "log REALIZED n", len(R["log_reg_real"]), "sum %+.4f" % sum(p for _, _, p in R["log_reg_real"]))
    pickle.dump(D, open(OUT, "wb")); print("wrote", OUT)
