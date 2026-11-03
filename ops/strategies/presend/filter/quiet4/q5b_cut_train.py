#!/usr/bin/env python3
"""QUIET4 step 5b: -20% followers for the earlier runs that have replay pickles (custom37: AMS r34 / r35 / r36, FRA r26 / r27 / r28;
read-only). Each run's armed windows are replayed at the run's OWN live config with their real tries, at 0% and at -20% outside buys
after our fill (REPS worlds), all windows together (knock-on). Per window: delta = value(-20%) - value(0%) (SOL, at the run's own size;
the scorer scales it x 0.696 / size like the live P&L). Out: /home/moiz/sniper-data/presend_quiet4/cut_train.json {run+reg: {"mint:slot": delta}}"""
import sys, json, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filter/quiet4")
import q3lib as Q
L = Q.L
REPS = 8
RUNS = {"r34": "r34AMS", "r35": "r35AMS", "r36": "r36AMS", "f26": "r26FRA", "f27": "r27FRA", "f28": "r28FRA"}


def main():
    out = {}
    for run, key in RUNS.items():
        X, wins, R = Q.load(run)
        lc = X["cfg"][-1]["presend_live"]; q = (lc.get("quiet") or {}).get("stop")
        cfg = dict(L.BASE, drop=lc["drop"], size=lc["spend"] / 1e9, k=lc["k"], win=lc["window_slots"], dl=lc["deadline_slots"], exit_ms=lc.get("exit_ms") or 10 ** 9,
                   exit_slots=lc["exit_slots"], tp=lc["tp"], sl=lc["sl"], qstop=tuple(int(v) for v in q.split(":")) if q else None)
        lp = L.live_positions(wins)
        v0 = {id(P): 0.0 for P in wins}; v2 = {id(P): 0.0 for P in wins}
        o0 = L.run_sim(wins, R, dict(cfg, cut=0.0), rep=0, livepos=lp)
        for P in wins: v0[id(P)] = Q.value(o0[id(P)])[1]
        for rep in range(REPS):
            o = L.run_sim(wins, R, dict(cfg, cut=0.2), rep=rep, livepos=lp)
            for P in wins: v2[id(P)] += Q.value(o[id(P)])[1] / REPS
        d = {f"{P.mint}:{P.s0}": v2[id(P)] - v0[id(P)] for P in wins}
        out[key] = d
        live = sum((P.live_pnl or 0) for P in wins) / 1e9
        print(key, "windows", len(wins), "replay 0%% %+.3f (live realized %+.3f) | -20%% %+.3f | size %.3f" % (sum(v0.values()), live, sum(v2.values()), cfg["size"]), flush=True)
    json.dump(out, open("/home/moiz/sniper-data/presend_quiet4/cut_train.json", "w"))


if __name__ == "__main__":
    main()
