#!/usr/bin/env python3
"""SPEED35 step 4: engine-faithful pre-send replay of every LIVE-armed window of AMS r36 + r37 where ONLY our landing timing
changes (s3 scenarios). Fill/exit rules = YOUNG sim (limit x0.88 re-read per slot, window trigger+10, whale-stop, QUIET stop),
run's own TP/SL (r36 20/20, r37 15/20), size 0.696, 3.52 mSOL per round trip; failed-try fees left out (same sends in every row).
Out: /home/moiz/sniper-data/speed35/replay.pkl + stdout tables."""
import pickle, datetime, collections, numpy as np
from multiprocessing import Pool
from s_sim import sim, LIVE_MIX, SCEN as YSCEN
D = "/home/moiz/sniper-data/speed35"
B = pickle.load(open(f"{D}/rows.pkl", "rb")); SC = pickle.load(open(f"{D}/scen.pkl", "rb"))
TPSL = {"r36": (0.20, 0.20), "r37": (0.15, 0.20)}
SIZE = 0.696; COST = 0.00352; SEEDS = 5
ROWS = [("cur", "cur"), ("young-ref", "young-ref")] + [(b, s) for b in ("prop50", "prop35", "prop25", "prop10", "shift35") for s in ("cur", b)]

def scen(run, name):
    if name == "young-ref": return YSCEN
    return SC[run][name]["scen"]  # renormalised over dumps inside the stream (window end handled by the sim itself)
def mix(run, name): return LIVE_MIX if name == "young-ref" else SC[run][name]["mix"]

def one(r):
    tp = B["tapes"].get(r["sig"])
    if not tp: return None
    tpv, slv = TPSL[r["run"]]; out = {}
    for b, s in ROWS:
        S = scen(r["run"], b); M = mix(r["run"], s)
        acc = [0.0, 0.0, 0.0]
        for sc, w in S:
            kw = dict(size=SIZE, lim_mult=0.88, tp=tpv, sl=slv, cost_rt=COST, scen=sc, mix=M)
            x = sim(r, tp, **kw)
            acc[0] += w * x["pnl"]; acc[1] += w * x["filled"]
            if x["filled"]:
                acc[2] += w * np.mean([sim(r, tp, cut=0.2, seed=k, **kw)["pnl"] for k in range(SEEDS)])
        out[(b, s)] = acc
    return {"sig": r["sig"], "run": r["run"], "t": r["t"], "lp": sum(x for x in r["real"] if x is not None) / 1e9, "lf": len(r["lfill"]), "res": out}

if __name__ == "__main__":
    todo = [r for r in B["rows"] if r["live"] == "armed" and B["tapes"].get(r["sig"])]
    with Pool(6) as p: R = [x for x in p.map(one, todo, chunksize=8) if x]
    pickle.dump(R, open(f"{D}/replay.pkl", "wb")); print("windows", len(R))
