#!/usr/bin/env python3
"""REARM2 day replay (offline, INFERRED): wsim2.run_x (rsim engine-faithful pre-send + dip22 200 ms exit measured live + QUIET skip
+ stop 6:2 + 40/s helius-ps caps) on one day, base and re-arm variants, N draws with common random numbers.
usage: run.py DAY --draws N [--scen base,R0,...] [--primary 0.65:0.2] [--procs 14] [--tag t]"""
import sys, os, pickle, time, argparse, collections, math
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/density")
import rlib, sim, dsim, drun, s48lib, wsim2
from multiprocessing import Pool
W = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/rearm2"
OUR = ("EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE")
SIZES = (0.40, 0.45, 0.65, 0.85, 1.00); TPS = (0.10, 0.20); CUTS = (0.0, 0.2, 0.4)
# variants: (wait slots, window slots, max age s, holder pct, quiet skip on re windows)
VAR = {"R0": (3, 20, 30, 6, False), "R1": (1, 20, 30, 6, False), "R2": (3, 10, 30, 6, False), "R3": (3, 20, 60, 6, False),
       "R4": (3, 20, 30, 8, False), "R5": (3, 20, 30, 6, True)}
G = {}


def re_windows(EV, v):
    wait, gs, age, pct, qs = v
    out = []
    for e in EV:
        if not e["ok"] or not e["v2"] or e["cashback"] or e["vsol"] >= 100e9: continue
        if e["age_s"] > age: continue
        n_h = e["nbig0"] if wait < 3 else e["nbig2"]; mp = e["maxpct0"] if wait < 3 else e["maxpct"]
        if n_h < 1 or mp < pct: continue
        if qs and e["qh"] is not None and e["qh"]["all4"]: continue
        ws = (e["nxt"][0], e["nxt"][1]) if e["nxt"] else None
        nb = e["nobig"]
        if nb is not None and (ws is None or tuple(nb) < ws): ws = tuple(nb)
        out.append(dict(kind="re", mint=e["mint"], slot=e["slot"] + wait, idx=0, j=0, en=e["slot"] + wait + gs, whale_sell=ws, k=8,
                        src=(e["slot"], e["idx"], e["seller"]), age_slots=e["age_slots"] + wait, bt=e["bt"], create_slot=e["create_slot"],
                        t2hit=e["t2hit"], maxpct=e["maxpct"]))
    return out


def spans(ws):
    sp = {}
    for x in ws:
        lo = x["create_slot"]; hi = (x["en"] if x["kind"] == "re" else x["slot"] + 10) + 70
        a, b = sp.get(x["mint"], (1 << 62, 0)); sp[x["mint"]] = (min(a, lo), max(b, hi))
    return sp


def make_cfg(size, tp):
    c = sim.Cfg(size=int(size * 1e9), k=8, drop=0.12, deadline_slots=1, window_slots=10, live_ms=50.0, whale_sell_ms=30.0, paths=[(40, 40)],
                global_rate=40, exit_slots=2, tp=tp, sl=0.20, whale_pct=6.0, create_slot=False, one_position=True, slot_ms=212.5)
    c.cost = sim.Cost(fail_fee=5000)
    c.routes = {"default": ["helius-ps"]}; c.path_rate = 40; c.path_scale = 1.0; c.far_too = False; c.follower_cut = 0.0; c.extra_lag_ms = 0.0
    c.max_pos = 1; c.quiet_stop = (6, 2); c.re_lag_ms = 0.0; c.guard = False
    return c


def row(r):
    t = r["trig"]
    d = dict(kind=t["kind"], mint=t["mint"], slot=t["slot"], bt=t["bt"], src=t.get("src"), armed=r["armed"], why=r["why"])
    if r["armed"]:
        d.update(filled=r["filled"], nfail=r["nfail"], sent=r["sent"], rate=r["rate"])
        if r["filled"]:
            d.update(fill_S=r["fill_S"], fill_I=r["fill_I"], base=r["base"], grid=r["grid"], flags=r["flags"], fill_d=r["fill_d"])
    return d


def job(a):
    name, d = a
    XC = dict(G["XC"]); XC["sent"] = collections.Counter(); XC["refused"] = collections.Counter()
    res = wsim2.run_x(G["ck"], G["store"], G["T2"] + G["REW"][name], G["cfg"], G["land"], G["model"], G["view"], 9100 + d, G["pm"], XC)
    return name, d, [row(r) for r in res], dict(XC["sent"]), dict(XC["refused"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("day", type=int); ap.add_argument("--draws", type=int, default=10); ap.add_argument("--scen", default="base," + ",".join(VAR))
    ap.add_argument("--primary", default="0.65:0.2"); ap.add_argument("--procs", type=int, default=14); ap.add_argument("--tag", default="main")
    ap.add_argument("--noquiet", action="store_true"); ap.add_argument("--dsell", default="all")
    A = ap.parse_args()
    t0 = time.time()
    Z = pickle.load(open(f"{W}/ev_D{A.day}.pkl", "rb"))
    T2 = [x for x in Z["T2"] if A.noquiet or not x["q"]["all4"]]
    scen = A.scen.split(",")
    REW = {"base": []}
    for s in scen:
        if s != "base": REW[s] = re_windows(Z["EV"], VAR[s])
    tp = rlib.Tape(tab=Z["tab"], with_ours=False)
    idm = tp.id_map(); our_ids = {idm[w] for w in OUR if w in idm}
    tp.drop_users = our_ids
    ck = tp.clock()
    allw = list(T2) + [x for v in REW.values() for x in v]
    store = sim.LazyStore(tp, spans(allw), maxn=6000)
    D3 = pickle.load(open(f"{s48lib.S48}/donors123.pkl", "rb"))
    pm = dsim.PathModel(); nm = drun.near_map()
    land = dsim.LandingX(D3, pm, nm, probes=("P3",)); model = s48lib.ModelN(D3, drun.s48_clock(), ("P1", "P2", "P3")); view = sim.View()
    sz, tpv = (float(x) for x in A.primary.split(":"))
    cfg = make_cfg(sz, tpv)
    SD = pickle.load(open(f"{W}/sell_delta.pkl", "rb"))
    runs = ("f28", "a34", "a35") if A.dsell == "all" else tuple(A.dsell.split("+"))
    dsell = [x for r in runs for x in SD[r].get("time-ms", [])]
    grid = [(int(s * 1e9), tp_, c) for s in SIZES for tp_ in TPS for c in CUTS]
    G.update(ck=ck, store=store, T2=T2, REW=REW, cfg=cfg, land=land, model=model, view=view, pm=pm,
             XC=dict(dsell=dsell, grid=grid, our_ids=our_ids))
    print(f"D{A.day}: T2 {len(Z['T2']):,} -> armable {len(T2):,} (quiet skip {'off' if A.noquiet else 'on'}); re windows " +
          ", ".join(f"{k} {len(v):,}" for k, v in REW.items() if k != "base") + f"; setup {time.time() - t0:.0f} s", flush=True)
    jobs = [(s, d) for s in scen for d in range(A.draws)]
    out = collections.defaultdict(dict)
    with Pool(A.procs) as p:
        for name, d, rows, sent, ref in p.imap_unordered(job, jobs):
            out[name][d] = dict(rows=rows, sent=sent, refused=ref)
            nf = sum(1 for r in rows if r.get("filled")); nre = sum(1 for r in rows if r.get("filled") and r["kind"] == "re")
            print(f"  {name} d{d}: fills {nf} (re {nre}) {time.time() - t0:.0f} s", flush=True)
    meta = dict(day=A.day, hours=Z["hours"], a=Z["a"], b=Z["b"], primary=(sz, tpv), quiet=not A.noquiet, n_re={k: len(v) for k, v in REW.items()}, grid=grid)
    pickle.dump(dict(meta=meta, out=dict(out)), open(f"{W}/res_D{A.day}_{A.tag}.pkl", "wb"))
    print(f"D{A.day}: done {time.time() - t0:.0f} s", flush=True)
