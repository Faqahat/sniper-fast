#!/usr/bin/env python3
"""QUIET4 step 5c: the stop rule N:M by the paired try-level replay on the earlier runs that have replay pickles (custom37: AMS r34-r36,
FRA r26-r28; read-only), at each run's OWN live config (live stop 6:2), real tries, all windows together (knock-on), REPS worlds;
a looser stop than live adds phantom tries after the live stop (INFERRED). Per window: value(S, cut) - value(live 6:2, 0%) (SOL at the
run's size). quiet3's stopgain shortcut disagrees with this replay on r37 (3:2: -0.04 vs +0.32 SOL), so these runs use the replay.
Out: /home/moiz/sniper-data/presend_quiet4/stop_train.pkl {run+reg: {"mint:slot": {(S, cut): delta}}}"""
import sys, pickle, collections, numpy as np
from multiprocessing import Pool
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filter/quiet4")
import q3lib as Q
L = Q.L
REPS = 6
RUNS = {"r34": "r34AMS", "r35": "r35AMS", "r36": "r36AMS", "f26": "r26FRA", "f27": "r27FRA", "f28": "r28FRA"}
STOPS = [(3, 2), (4, 2), (5, 2), (6, 2), (7, 2), (8, 2), (4, 3), (5, 3), (6, 3), (7, 3), (8, 3)]


def one(run):
    X, wins, R = Q.load(run)
    lc = X["cfg"][-1]["presend_live"]; q = (lc.get("quiet") or {}).get("stop")
    cfg = dict(L.BASE, drop=lc["drop"], size=lc["spend"] / 1e9, k=lc["k"], win=lc["window_slots"], dl=lc["deadline_slots"], exit_ms=lc.get("exit_ms") or 10 ** 9,
               exit_slots=lc["exit_slots"], tp=lc["tp"], sl=lc["sl"], qstop=tuple(int(v) for v in q.split(":")) if q else None)
    lp = L.live_positions(wins)
    o0 = L.run_sim(wins, R, dict(cfg, cut=0.0), rep=0, livepos=lp)
    base = {id(P): Q.value(o0[id(P)])[1] for P in wins}
    res = collections.defaultdict(dict); tot = {}
    for S in STOPS:
        for cut in (0.0, 0.2):
            acc = collections.defaultdict(float)
            reps = 1 if (S == cfg["qstop"] and cut == 0.0) else REPS
            for rep in range(reps):
                o = L.run_sim(wins, R, dict(cfg, qstop=S, cut=cut), rep=rep, livepos=lp)
                for P in wins: acc[id(P)] += Q.value(o[id(P)])[1] / reps
            for P in wins: res[f"{P.mint}:{P.s0}"][(S, cut)] = acc[id(P)] - base[id(P)]
            tot[(S, cut)] = sum(acc.values()) - sum(base.values())
    return RUNS[run], dict(res), tot, cfg["size"]


def main():
    out = {}
    with Pool(6) as pool:
        for key, res, tot, size in pool.imap_unordered(one, list(RUNS)):
            out[key] = res
            print(key, "size", size, " ".join(f"{S[0]}:{S[1]} {tot[(S, 0.0)]:+.3f}" for S in STOPS), flush=True)
    pickle.dump(out, open("/home/moiz/sniper-data/presend_quiet4/stop_train.pkl", "wb"))


if __name__ == "__main__":
    main()
