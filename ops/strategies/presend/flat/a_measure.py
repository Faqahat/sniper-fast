#!/usr/bin/env python3
"""FLAT study, IDEA A (MEASURED inputs): (1) the live TP / SL reaction delay on DEV (trigger trade -> our sell landing, chain ms);
(2) the live time-exit delay of each position; (3) the replay's identity check: replaying the live exit (N = 2) on the chain tape
must give back every live sell's SOL exactly. Writes /home/moiz/sniper-data/presend_flat/a_delays.json
usage: a_measure.py r24 r25 r26"""
import sys, json, collections
import numpy as np
import flatlib as FL, a_core as AC

def main():
    runs = sys.argv[1:]
    C = FL.Chain((1,))
    dl = []; dt = []; ident = collections.Counter(); bad = []
    for run in runs:
        B = FL.load_base(run)
        for w in B["W"]:
            if not w["filled"]: continue
            P = AC.prep(C, w)
            if P is None: ident["no_prep"] += 1; continue
            ex = w["exit"]
            if ex["why"] in ("take-profit", "stop-loss"):
                f = w["fill"]
                seen = [z for z in w["tape"] if z["user"] != FL.AMS and z["t"] <= ex["t"] and (z["slot"], z["idx"], z["j"]) > (f["slot"], f["idx"], 0)]
                if seen:
                    z = seen[-1]
                    dl.append(P["cc_sell"] - C.cc(z["slot"], z["idx"]))
            elif ex["why"] == "time-limit":
                dt.append(P["d_time"])
                r = AC.walk(P, dict(N=2), d_react=0.0, check=True)
                ok = (r["net"] == P["net_live"]) and r["mism"] == 0
                ident["time_ok" if ok else "time_bad"] += 1
                if not ok and len(bad) < 5: bad.append((run, w["mint"][:8], r["net"], P["net_live"], r["mism"], r["why"]))
    dl = np.array(dl); dt = np.array(dt)
    out = dict(d_react_median=float(np.median(dl)), d_react_pcts=[round(float(x), 1) for x in np.percentile(dl, [10, 25, 50, 75, 90])], n_react=len(dl),
               d_time_median=float(np.median(dt)), d_time_pcts=[round(float(x), 1) for x in np.percentile(dt, [10, 25, 50, 75, 90])], n_time=len(dt), identity=dict(ident))
    json.dump(out, open(f"{FL.D}/a_delays.json", "w"), indent=1)
    print(json.dumps(out)); print("identity failures (first 5):", bad)
main()
