#!/usr/bin/env python3
"""FILTERS step 2: the joint replay (ma4_sim, rule R0 = T2 + live re-arm at 0.65 SOL) under every combination of the four filters
(ma15_filters: LW, DL2 / DLa, BC, STo / STn) x reps, in parallel, plus the T2-only reference ("T2only": no re-arm, no filter).
One compact pickle per (combo, rep) in OUTDIR (ma6_run's row format, so ma7_tables reads it).
usage: ma16_run.py CTX.pkl OUTDIR [--reps 8] [--procs 8] [--only a,b]"""
import sys, os, json, pickle, time, argparse
from multiprocessing import Pool
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/multiarm")
from ma6_run import KEEP

_W = None; _H = None


def init(ctxp):
    global _W, _H
    import ma4_sim as S, ma15_filters as F
    _W = S.World(ctxp); _H = F.Hazard()


def one(args):
    name, rep, outdir = args
    import ma4_sim as S, ma15_filters as F, ma_lib as M
    out = f"{outdir}/{name}__{rep}.pkl"
    if os.path.exists(out): return name, rep, "cached"
    t0 = time.time()
    if name == "T2only": res, meta = S.simulate(_W, None, rep)
    else:
        flt = F.Filters(name, _W.run, _W.tape, _H)
        res, meta = S.simulate(_W, M.Rule("R0"), rep, flt=flt)
    rows = [{k: r.get(k) for k in KEEP} for r in res]
    tmp = out + ".tmp"
    pickle.dump({"name": name, "rule": name, "rep": rep, "rows": rows, "meta": meta}, open(tmp, "wb"))
    os.replace(tmp, out)
    nf = sum(r["filled"] for r in res); c = sum(r["cash"] for r in res)
    fs = {k: v for k, v in meta["stats"].items() if k.startswith("flt_")}
    sk = {k: v for k, v in meta["skips"].items() if k in ("t2_lw", "t2_bc", "rearm_bc")}
    return name, rep, f"{len(res)} windows {nf} fills cash {c:+.3f} {fs} {sk} in {time.time() - t0:.0f}s"


if __name__ == "__main__":
    import ma15_filters as F
    ap = argparse.ArgumentParser(); ap.add_argument("ctx"); ap.add_argument("outdir")
    ap.add_argument("--reps", type=int, default=8); ap.add_argument("--procs", type=int, default=8); ap.add_argument("--only", default=None)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    names = ["T2only"] + F.combos()
    if a.only: names = [n for n in names if n in a.only.split(",")]
    jobs = [(n, rep, a.outdir) for rep in range(a.reps) for n in names]
    t0 = time.time()
    with Pool(a.procs, initializer=init, initargs=(a.ctx,)) as p:
        for k, (n, rep, msg) in enumerate(p.imap_unordered(one, jobs)):
            print(f"[{k + 1}/{len(jobs)} {time.time() - t0:.0f}s] {n} rep {rep}: {msg}", flush=True)
    print("DONE", flush=True)
