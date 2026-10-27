#!/usr/bin/env python3
"""LIVE27 step 2 (read-only, offline): replay run 27's pre-send windows with and without QUIET, N draws per stream.
Streams (window lists; every window draws from its own generator, so a window behaves the same in every stream unless the rule
change or the interactions it causes reach it):
  cal  : the 177 live windows forced armed, the live QUIET stops at their live times, the model free (calibration vs live)
  A0   : as live: the 177 windows; the 45 stopped windows stop at their live time and their tries before the stop cannot fill
         (MEASURED: none did)
  B    : no QUIET: the 177 windows (the 45 run past their stop; tries before it still cannot fill) + the 36 skipped triggers armed,
         no stop rule anywhere
  C    : skip rule off only: A0 + the 36 skipped triggers armed WITH the modeled stop rule
  D    : stop rule off only: the 177 windows, the 45 run past their stop, no skipped triggers
  iso  : every one of the 36 skipped (full window; and with the modeled stop) and of the 45 stopped (after the stop) alone
Live windows in A0/B/C/D use the dynamic arm checks (blocked_armed / blocked_position), as the engine would; cal forces them.
usage: replay27.py --pool P3|R27 [--draws 400] [--procs 10] [--streams cal,A0,B,C,D,iso] [--cut 0.2 --tag cut20]"""
import sys, os, json, pickle, argparse, collections, time, copy
import numpy as np
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import setup27 as S
import lib27 as L
import sim27

G = {}


def row(r):
    return dict(armed=r["armed"], why=r.get("why"), filled=bool(r.get("filled", False)), pnl=int(r.get("pnl", 0)), fees=int(r.get("fees", 0)),
                net=int(r.get("net", 0)), exit=r.get("exit"), fill_d=r.get("fill_d"), fill_S=r.get("fill_S"), fees_after=r.get("fees_after"),
                fees_before=r.get("fees_before"), sent_after=r.get("sent_after"), q_dec=r.get("q_dec"), q_others=r.get("q_others"), q_stop=r.get("q_stop"),
                sent=r.get("sent", 0), landed=r.get("landed", 0), deadline=r.get("deadline", 0), rate=sum((r.get("rate") or {}).values()),
                paused=r.get("paused", 0), sas=dict(r.get("sas") or {}), curve=r.get("curve"), xgap=r.get("xgap"))


def wl(stream):
    live, skip = G["live"], G["skip"]
    out = []
    for x in live:
        y = dict(x); y["key"] = ("L", x["w"])
        if stream == "cal":
            y["force_arm"] = True
            if x["d_stop"] is not None: y["stop_at_d"] = x["d_stop"]
        else:
            y["dyn_only"] = True
            if x["d_stop"] is not None:
                y["nofill_before_d"] = x["d_stop"]
                if stream in ("A0", "C"): y["stop_at_d"] = x["d_stop"]
        out.append(y)
    if stream in ("B", "C"):
        for i, x in enumerate(skip):
            y = dict(x); y["key"] = ("S", i); y["dyn_only"] = True
            if stream == "C": y["qmodel"] = True
            out.append(y)
    return out


def iso_lists():
    """single-window runs: the 36 skipped (no stop / modeled stop) and the 45 stopped (stopped at live time / run past it)"""
    L_ = []
    for i, x in enumerate(G["skip"]):
        y = dict(x); y["key"] = ("S", i); y["dyn_only"] = True; L_.append(("skip_full", [y]))
        z = dict(y); z["qmodel"] = True; L_.append(("skip_qstop", [z]))
    for x in G["live"]:
        if x["d_stop"] is None: continue
        y = dict(x); y["key"] = ("L", x["w"]); y["force_arm"] = True; y["nofill_before_d"] = x["d_stop"]
        L_.append(("stop_after", [y]))
        z = dict(y); z["stop_at_d"] = x["d_stop"]; L_.append(("stop_live", [z]))
    return L_


def one(job):
    stream, seed = job
    cfg = G["cfg"]
    kw = dict(our_id=G["our_id"], whale_ids=G["whale_ids"], qdelta_pool=G["qdelta_pool"])
    if stream == "iso":
        out = collections.defaultdict(dict)
        for name, ws in G["iso"]:
            res = sim27.run27(G["ck"], G["store"], copy.deepcopy(ws), cfg, G["landing"], G["model"], G["view"], seed, exclude_self=True, **kw)
            for x, r in zip(ws, res): out[name][x["key"]] = row(r)
        return stream, seed, dict(out)
    ws = G["lists"][stream]
    res = sim27.run27(G["ck"], G["store"], copy.deepcopy(ws), cfg, G["landing"], G["model"], G["view"], seed, exclude_self=True, **kw)
    by = {}
    for r in res: by[r["trig"]["key"]] = row(r)
    return stream, seed, by


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default="P3"); ap.add_argument("--draws", type=int, default=400); ap.add_argument("--procs", type=int, default=10)
    ap.add_argument("--streams", default="cal,A0,B,C,D,iso"); ap.add_argument("--cut", type=float, default=0.0); ap.add_argument("--tag", default="main")
    ap.add_argument("--lag", type=float, default=0.0)
    A = ap.parse_args()
    t0 = time.time()
    G.update(S.setup())
    G["landing"] = G["land"][A.pool]
    G["cfg"].follower_cut = A.cut; G["cfg"].extra_lag_ms = A.lag
    streams = A.streams.split(",")
    G["lists"] = {s: wl(s) for s in streams if s != "iso"}
    G["iso"] = iso_lists()
    meta = dict(pool=A.pool, draws=A.draws, cut=A.cut, lag=A.lag, slot_ms=G["slot_ms"], streams=streams,
                live=[dict(key=("L", x["w"]), w=x["w"], mint=x["mint"], slot=x["slot"], idx=x["idx"], t_ns=x["t_ns"], phase=x["phase"], all4=x["all4"],
                           d_stop=x["d_stop"], whale_sell=x["whale_sell"], live=x["live"], pct=x["pct"]) for x in G["live"]],
                skip=[dict(key=("S", i), mint=x["mint"], slot=x["slot"], idx=x["idx"], t_ns=x["t_ns"], phase="on", whale_sell=x["whale_sell"], pct=x["pct"],
                           sig=x["sig"], whale=x["whale_b58"]) for i, x in enumerate(G["skip"])])
    for k in ("R", "tp"): G.pop(k, None)
    import gc; gc.collect()
    jobs = [(s, 5000 + d) for s in streams for d in range(A.draws)]
    out = collections.defaultdict(list)
    with Pool(A.procs) as p:
        for stream, seed, by in p.imap_unordered(one, jobs, chunksize=4):
            out[stream].append((seed, by))
    for s in out: out[s].sort(key=lambda z: z[0])
    fn = f"{L.DATA}/replay27_{A.pool}_{A.tag}.pkl"
    pickle.dump(dict(meta=meta, out=dict(out)), open(fn, "wb"))
    print(f"wrote {fn}: streams {streams}, {A.draws} draws, {time.time() - t0:.0f} s")
