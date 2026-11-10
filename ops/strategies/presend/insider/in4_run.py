#!/usr/bin/env python3
"""INSIDER step 4: run the joint replay (in3_sim) for the base (T2 + R0) and the INSIDER variants x reps on one run, in parallel
(the World and the insider facts are built once in the parent; workers fork from it). One pickle per (variant, rep) in OUTDIR.
usage: in4_run.py CTX.pkl OUTDIR [--reps 4] [--procs 5] [--only NAME,NAME]"""
import sys, os, json, pickle, time, argparse
from multiprocessing import get_context
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/insider")
import in3_sim as I
import ma_lib as M

KEEP = ("key", "kind", "mint", "t_arm", "end_why", "ticks", "sent", "refused", "paused", "fails", "filled", "nth", "chained", "dump_age", "n_hold",
        "fs", "fi", "t_fill", "t_close", "c_sell", "why", "p_entry", "gross_naive", "d_slip", "d_cut", "cash_naive", "cash", "cash_cut", "followers", "dropped",
        "ins_u", "ins_pct", "ins_solo", "s0", "isell_slot", "sell_slot")
R0 = {"name": "R0"}


def variants():
    V = {"BASE": None}
    for mode in I.MODES:
        for X in I.XS:
            for W in (5, 10, 15, 20):
                V[f"INS_{mode}_X{X}_W{W}"] = {"mode": mode, "X": X, "W": W}
    V["INS_x_X10_W10_solo"] = {"mode": "x", "X": 10, "W": 10, "solo": True}
    V["INS_x_X15_W10_solo"] = {"mode": "x", "X": 15, "W": 10, "solo": True}
    return V


_W = None; _F = None


def one(args):
    name, irule, rep, outdir = args
    out = f"{outdir}/{name}__{rep}.pkl"
    if os.path.exists(out): return name, rep, "cached"
    t0 = time.time()
    res, meta = I.simulate(_W, M.Rule(**R0), rep, irule=irule, facts=_F)
    rows = [{k: r.get(k) for k in KEEP} for r in res]
    tmp = out + ".tmp"
    pickle.dump({"name": name, "irule": irule, "rep": rep, "rows": rows, "meta": meta}, open(tmp, "wb"))
    os.replace(tmp, out)
    nf = sum(r["filled"] for r in res if r["kind"] == "ins"); c = sum(r["cash"] for r in res)
    ni = sum(1 for r in res if r["kind"] == "ins")
    return name, rep, f"{len(res)} windows ({ni} ins, {nf} ins fills) cash {c:+.3f} in {time.time() - t0:.0f}s"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("ctx"); ap.add_argument("outdir")
    ap.add_argument("--reps", type=int, default=4); ap.add_argument("--procs", type=int, default=5); ap.add_argument("--only", default=None)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    t0 = time.time()
    _W = I.S.World(a.ctx)
    _F = I.ins_facts(_W)
    print(f"world + facts in {time.time() - t0:.0f}s: {len(_F[0])} arms, {_F[2]}", flush=True)
    pickle.dump({"arms": [{k: v for k, v in x.items()} for x in _F[0]], "meta": _F[2], "hours": (_W.t_end - _W.t_start) / 3.6e6, "t_start": _W.t_start},
                open(f"{a.outdir}/facts.pkl", "wb"))
    V = variants()
    if a.only: V = {k: v for k, v in V.items() if k in a.only.split(",")}
    jobs = [(name, irule, rep, a.outdir) for rep in range(a.reps) for name, irule in V.items()]
    # warm the R0 candidate cache (tape.tok) in the parent so the forked workers share it
    I.simulate(_W, M.Rule(**R0), 0, irule=None, facts=_F)
    print(f"warm base in {time.time() - t0:.0f}s", flush=True)
    ctx = get_context("fork")
    with ctx.Pool(a.procs) as p:
        for k, (name, rep, msg) in enumerate(p.imap_unordered(one, jobs)):
            print(f"[{k + 1}/{len(jobs)} {time.time() - t0:.0f}s] {name} rep {rep}: {msg}", flush=True)
    print("DONE", flush=True)
