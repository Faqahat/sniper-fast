#!/usr/bin/env python3
"""REARM step 2 (read-only): VALIDATE the pre-send replay on our live pre-send runs before adding anything.
The density study's calibration stream ('cal': every live window forced armed at its live trigger, the live QUIET stops kept, the
run's own live settings: k, rate caps, size, deadline, window, exits, one position; landing = P3 donor transplant; view, follower
and cost models of presend/real/sim.py), run with presend/density/dsim.run_d UNCHANGED, on tapes cut from the dv8 recording
(r1_tapes.py) instead of the density study's per-run tapes. Runs: AMS r24..r33 and FRA r26 (its windows before the tape's end).
Live numbers (MEASURED, dlib.load_run): fills, realized P&L + rent back, failed-try fees from the engine's landing records.
usage: r2_validate.py RUN[,RUN..] [--draws 40] [--procs 3]   (RUN = a24..a33, f26)    Out: val_<run>.pkl"""
import sys, os, json, pickle, argparse, time, collections
import numpy as np
from multiprocessing import Pool
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/density")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real")
import dlib, dsim, drun, sim, s48lib

OUT = "/home/moiz/sniper-data/haqq_dissect/rearm"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r1_tapes import RUNS as RECS
TAPE_END = 1793131823          # dv8 tape: last block time (10-28 01:12 PKT)
G = {}


_load = dlib.load_run


def load_cut(path):
    """dlib.load_run, windows armed before the tape's end only"""
    R = _load(path)
    for w in [w for w, x in R["W"].items() if x["arm"]["trig"]["t"] / 1e9 >= TAPE_END - 120]: del R["W"][w]
    return R


dlib.load_run = load_cut


def setup(run):
    n = int(run[1:])
    dlib.RUNS[n] = dict(rec=RECS[run], tab=f"{OUT}/tab_{run}")
    if run.startswith("f"): dlib.WALLET = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"
    S = dlib.setup_run(n)
    S["live"] = [x for x in S["live"] if x["t_ns"] / 1e9 < TAPE_END - 120]
    return S


def one(job):
    seed = job
    S = G["S"]
    drun.G_["S"] = S
    ws = drun.wlist("cal")
    res = dsim.run_d(S["ck"], S["store"], ws, G["cfg"], G["land"], G["model"], G["view"], seed, G["pm"], exclude_self=True,
                     our_id=S["our_id"], whale_ids=S["whale_ids"])
    by = {}
    for r in res:
        k = r["trig"]["w"]
        if not r["armed"]: by[k] = (0, 0, 0, 0, 0); continue
        by[k] = (1, int(r["filled"]), int(r["pnl"]), int(r["fees"]), int(r.get("sent", 0)))
    return seed, by


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("runs"); ap.add_argument("--draws", type=int, default=40); ap.add_argument("--procs", type=int, default=3)
    A = ap.parse_args()
    D3 = pickle.load(open(f"{s48lib.S48}/donors123.pkl", "rb"))
    pm = dsim.PathModel(); nm = drun.near_map()
    G["pm"] = pm; G["land"] = dsim.LandingX(D3, pm, nm, probes=("P3",)); G["model"] = s48lib.ModelN(D3, drun.s48_clock(), ("P1", "P2", "P3")); G["view"] = sim.View()
    for run in A.runs.split(","):
        t0 = time.time()
        S = setup(run)
        G["S"] = S; G["cfg"] = drun.make_cfg(S["cfg"], "cal")
        S.pop("R", None)
        print(f"{run}: {len(S['live'])} windows, size {S['cfg'].size / 1e9:.2f}, k {S['cfg'].k}, rate {S['cfg'].global_rate}, slot_ms {S['slot_ms']:.1f}, setup {time.time() - t0:.0f} s", flush=True)
        with Pool(A.procs) as p:
            out = sorted(p.map(one, [9000 + d for d in range(A.draws)]), key=lambda z: z[0])
        meta = dict(run=run, size=S["cfg"].size, k=S["cfg"].k, rate=S["cfg"].global_rate, hours=S["hours"],
                    live=[dict(w=x["w"], mint=x["mint"], t_ns=x["t_ns"], dumped=x["dumped"], d_stop=x["d_stop"], live=x["live"]) for x in S["live"]])
        pickle.dump(dict(meta=meta, out=out), open(f"{OUT}/val_{run}.pkl", "wb"))
        print(f"{run}: done {time.time() - t0:.0f} s", flush=True)
