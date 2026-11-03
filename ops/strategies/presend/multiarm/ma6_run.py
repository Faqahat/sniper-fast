#!/usr/bin/env python3
"""MULTIARM step 6: run the joint replay (ma4_sim) for a list of rule variants x reps on one run, in parallel; one compact pickle per
(variant, rep) in OUTDIR (rows: one per window).
usage: ma6_run.py CTX.pkl VARIANTS.json OUTDIR [--reps 8] [--procs 8] [--only NAME,NAME]"""
import sys, os, json, pickle, time, argparse
from multiprocessing import Pool
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/multiarm")

KEEP = ("key", "kind", "mint", "t_arm", "end_why", "ticks", "sent", "refused", "paused", "fails", "filled", "nth", "chained", "dump_age", "n_hold",
        "fs", "fi", "t_fill", "t_close", "c_sell", "why", "p_entry", "gross_naive", "d_slip", "d_cut", "cash_naive", "cash", "cash_cut", "followers", "dropped")
_W = None


def init(ctxp):
    global _W
    import ma4_sim as S
    _W = S.World(ctxp)


def one(args):
    name, rule, rep, outdir = args
    import ma4_sim as S
    out = f"{outdir}/{name}__{rep}.pkl"
    if os.path.exists(out): return name, rep, "cached"
    t0 = time.time()
    res, meta = S.simulate(_W, S.rule_from(rule), rep)
    rows = [{k: r.get(k) for k in KEEP} for r in res]
    tmp = out + ".tmp"
    pickle.dump({"name": name, "rule": rule, "rep": rep, "rows": rows, "meta": meta}, open(tmp, "wb"))
    os.replace(tmp, out)
    nf = sum(r["filled"] for r in res); c = sum(r["cash"] for r in res)
    return name, rep, f"{len(res)} windows {nf} fills cash {c:+.3f} in {time.time() - t0:.0f}s"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("ctx"); ap.add_argument("variants"); ap.add_argument("outdir")
    ap.add_argument("--reps", type=int, default=8); ap.add_argument("--procs", type=int, default=8); ap.add_argument("--only", default=None)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    V = json.load(open(a.variants))
    if a.only: V = {k: v for k, v in V.items() if k in a.only.split(",")}
    jobs = [(name, rule, rep, a.outdir) for rep in range(a.reps) for name, rule in V.items()]
    t0 = time.time()
    with Pool(a.procs, initializer=init, initargs=(a.ctx,)) as p:
        for k, (name, rep, msg) in enumerate(p.imap_unordered(one, jobs)):
            print(f"[{k + 1}/{len(jobs)} {time.time() - t0:.0f}s] {name} rep {rep}: {msg}", flush=True)
    print("DONE", flush=True)
