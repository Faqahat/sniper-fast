#!/usr/bin/env python3
"""REARM step 4 (read-only, offline; INFERRED): the day replay with the engine's own pre-send rules (rsim.run_x), per test day:
  base   = the live pre-send as configured now (T2 whale-buy windows, k 8, helius-ps 40/s path + global, size 0.40, limit 0.88 x the
           latest seen price, deadline +1 slot, window 10 slots / whale's first sell + 30 ms, TP 10 % / SL 20 % / 2-slot exit, one
           position, QUIET stop 6:2; the QUIET skip (whale history) is NOT modelled);
  re_<c> = base + the re-arm windows of config c (X = paid threshold on r2, G = window slots, A = max token age s at the paid dump,
           K = tries per pace slot of a re window, H = 1: only if a wallet holds >= 6 % at the end of slot dump+2; H = 2: that, and the
           window is also stopped 30 ms after the engine sees the trade after which no wallet holds >= 6 % (r3b_holders.py, evh_D<k>.pkl)).
Every window has its own random generator (common random numbers): re_<c> - base is the re-arm's effect incl. its knock-on on the
normal windows (one position, rate caps, token blocks). Out: res_D<k>_<tag>.pkl (compact per-window rows per draw), and with
--log the decisions of draw 0 of each config.
usage: r4_days.py DAY --cfgs X:G:A:K:H,... [--draws 2] [--tag t] [--log] [--k 8] [--rate 40] [--size 0.40] [--noquiet]"""
import sys, os, json, pickle, time, argparse, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/density")
import rlib, sim, dsim, drun, s48lib, rsim
from r3_events import our_sighs

OUT = "/home/moiz/sniper-data/haqq_dissect/rearm"


def parse_cfg(s):
    x, g, a, k, h = s.split(":")
    return dict(X=None if x == "any" else float(x), G=int(g), A=float(a), K=int(k), H=int(h), name=s)


def re_windows(EV, c, EVH=None):
    out = []
    for e in EV:
        if not e["ok"] or not e["v2"] or e["cashback"] or e["vsol"] >= 100e9: continue
        if c["X"] is not None and e["r2"] < c["X"]: continue
        if e["age_s"] > c["A"]: continue
        if c["H"] and e["nbig2"] < 1: continue
        ws = (e["nxt"][0], e["nxt"][1]) if e["nxt"] else None
        if c["H"] == 2:
            nb = EVH[(e["mint"], e["slot"], e["idx"])]
            if nb is not None and (ws is None or tuple(nb) < ws): ws = tuple(nb)
        out.append(dict(kind="re", mint=e["mint"], slot=e["slot"] + 3, idx=0, j=0, en=e["slot"] + 3 + c["G"], whale_sell=ws, k=c["K"],
                        guard=(e["nxt"][0], e["nxt"][1]) if e["nxt"] else None,
                        src=(e["slot"], e["idx"], e["seller"]), r2=e["r2"], age_slots=e["age_slots"] + 3, src_kth=e["kth"], src_t2hit=e["t2hit"]))
    return out


def spans(ws):
    sp = {}
    for x in ws:
        lo = x["slot"] - 45; hi = (x["en"] if x["kind"] == "re" else x["slot"] + 10) + 70
        a, b = sp.get(x["mint"], (1 << 62, 0)); sp[x["mint"]] = (min(a, lo), max(b, hi))
    return sp


def make_cfg(A):
    c = sim.Cfg(size=int(A.size * 1e9), k=A.k, drop=0.12, deadline_slots=1, window_slots=getattr(A, "t2win", 10), live_ms=50.0, whale_sell_ms=30.0, paths=[(A.rate, A.rate)],
                global_rate=A.rate, exit_slots=2, tp=0.10, sl=0.20, whale_pct=6.0, create_slot=False, one_position=True, slot_ms=212.5)
    c.cost = sim.Cost(fail_fee=5120)
    c.routes = {"default": ["helius-ps"]}; c.path_rate = A.rate; c.path_scale = 1.0; c.far_too = False; c.follower_cut = 0.0; c.extra_lag_ms = 0.0
    c.max_pos = 1; c.quiet_stop = None if A.noquiet else (6, 2); c.extra_lag_ms = getattr(A, "lag", 0.0); c.re_lag_ms = getattr(A, "relag", 0.0); c.guard = "re" if getattr(A, "guard_re", False) else getattr(A, "guard", False)
    return c


def row(r):
    t = r["trig"]
    key = (t["kind"], t["mint"], t["slot"], t["idx"], t.get("j", 0), t.get("whale_sell"), t.get("src"), t.get("r2"))
    if not r["armed"]: return (key, 0, r["why"], 0, 0, 0, 0, 0, None)
    ex = None
    if r["filled"]:
        ex = (r["fill_S"], r["path"], {k: (v["gross"], v["why"]) for k, v in r["ex"].items()})
    return (key, 1, r["why"], int(r["filled"]), r["nfail"], r["sent"], r["rate"], r["paused"], ex)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("day", type=int); ap.add_argument("--cfgs", default=""); ap.add_argument("--draws", type=int, default=2); ap.add_argument("--tag", default="t")
    ap.add_argument("--log", action="store_true"); ap.add_argument("--k", type=int, default=8); ap.add_argument("--rate", type=int, default=40)
    ap.add_argument("--size", type=float, default=0.40); ap.add_argument("--noquiet", action="store_true"); ap.add_argument("--nobase", action="store_true")
    ap.add_argument("--lag", type=float, default=0.0, help="stress: extra landing delay (ms) on every attempt (T2 and re)")
    ap.add_argument("--relag", type=float, default=0.0, help="stress: extra landing delay (ms) on re-arm attempts only")
    ap.add_argument("--guard", action="store_true", help="holder guard: a buy executes only after the whale's sale (see rsim)")
    ap.add_argument("--guard-re", action="store_true", help="the holder guard on re-arm windows only (T2 windows as today)")
    ap.add_argument("--t2win", type=int, default=10, help="T2 window slots (live 10)")
    A = ap.parse_args()
    t0 = time.time()
    Z = pickle.load(open(f"{OUT}/ev_D{A.day}.pkl", "rb"))
    T2 = Z["T2"]; EV = Z["EV"]
    cfgs = [parse_cfg(s) for s in A.cfgs.split(",") if s]
    EVH = pickle.load(open(f"{OUT}/evh_D{A.day}.pkl", "rb")) if any(c["H"] == 2 for c in cfgs) else None
    REW = {c["name"]: re_windows(EV, c, EVH) for c in cfgs}
    allw = list(T2) + [x for v in REW.values() for x in v]
    tp = rlib.Tape(tab=f"{OUT}/tab_D{A.day}", with_ours=False); tp.skip_sigh = our_sighs()
    ck = tp.clock()
    store = sim.LazyStore(tp, spans(allw), maxn=4000)
    D3 = pickle.load(open(f"{s48lib.S48}/donors123.pkl", "rb"))
    pm = dsim.PathModel(); nm = drun.near_map()
    land = dsim.LandingX(D3, pm, nm, probes=("P3",)); model = s48lib.ModelN(D3, drun.s48_clock(), ("P1", "P2", "P3")); view = sim.View()
    cfg = make_cfg(A)
    print(f"D{A.day}: T2 {len(T2):,}, re windows " + ", ".join(f"{k} {len(v):,}" for k, v in REW.items()) + f" (setup {time.time() - t0:.0f} s)", flush=True)
    out = {}; logs = {}
    scen = ([("base", [])] if not A.nobase else []) + [(c["name"], REW[c["name"]]) for c in cfgs]
    for name, rw in scen:
        out[name] = []
        for d in range(A.draws):
            t1 = time.time()
            res = rsim.run_x(ck, store, list(T2) + rw, cfg, land, model, view, 9100 + d, pm, log=(A.log and d == 0 and name != "base"))
            out[name].append([row(r) for r in res])
            if A.log and d == 0 and name != "base":
                logs[name] = [(r["trig"], r["log"], {k: v for k, v in r.items() if k not in ("trig", "log")}) for r in res if r["trig"]["kind"] == "re"]
            nf = sum(1 for r in res if r.get("filled")); nre = sum(1 for r in res if r.get("filled") and r["trig"]["kind"] == "re")
            print(f"  D{A.day} {name} draw {d}: fills {nf} (re {nre}) {time.time() - t1:.0f} s", flush=True)
    meta = dict(guard="re" if A.guard_re else A.guard, t2win=A.t2win, lag=A.lag, relag=A.relag, day=A.day, k=A.k, rate=A.rate, size=A.size, quiet=not A.noquiet, cfgs=cfgs, n_t2=len(T2), n_re={k: len(v) for k, v in REW.items()})
    pickle.dump(dict(meta=meta, out=out), open(f"{OUT}/res_D{A.day}_{A.tag}.pkl", "wb"))
    if logs: pickle.dump(logs, open(f"{OUT}/log_D{A.day}_{A.tag}.pkl", "wb"))
    print(f"D{A.day}: done {time.time() - t0:.0f} s", flush=True)
