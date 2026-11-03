#!/usr/bin/env python3
"""COMP-REARM day replay (offline, INFERRED): rearm2/wsim2.run_x (engine-faithful pre-send replay: donor landing, k tries/slot,
40/s caps, one position, QUIET skip + stop 6:2, live 200 ms exit measured live) with today's base (T2 whale >= 6%) plus extra
'competitor' windows (kind 're' in wsim2: armed at the competitor's buy, 10 slots, k 8, limit = latest price x 0.88).
Scenarios share random numbers with base, so delta = scenario - base includes every interaction (blocked base windows, cap).
usage: run.py DAYTAG --draws N --scen base,A0,...  (DAYTAG = D2..D6, D7 (tabN 1.9 h), D7b (r37 hours, wave37 tape))"""
import sys, os, pickle, time, argparse, collections, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
for p in ("real", "density", "rearm2"): sys.path.insert(0, f"/home/moiz/sniper/ops/strategies/presend/{p}")
import rlib, sim, dsim, drun, s48lib, wsim2
from multiprocessing import Pool
from comps import COMP
D = "/home/moiz/sniper-data/comp_rearm"
RW = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/rearm2"
OUR = ("EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE")
HI = {"8yYMhu", "haqq", "HkQ7", "CZ77", "6VzX", "A2ka"}          # bots with the highest 10-slot >=12% drop rate after their buy (phys.md, all days)
# scenario: filter on a competitor-buy row (+ T2 context) ; window slots
def f_A0(r, c): return r["sol"] >= 0.7e9
def f_A1(r, c): return r["who"] in HI
def f_A2(r, c): return r["who"] in HI and r["n_comp"] <= 2
def f_A3(r, c): return r["who"] in ("CZ77", "A2ka", "6VzX")
def f_A4(r, c): return r["who"] in ("haqq", "8yYMhu")
def f_B0(r, c): return c["after_t2"]                              # any competitor buy after our base window on that token ended
def f_B1(r, c): return c["after_t2"] and r["who"] in HI
def f_C1(r, c): return c["swarm"]                                 # >= 2 different competitors bought in the last 2 slots
def f_C2(r, c): return r["who"] in HI and r["n_comp"] <= 2 and r["sol"] >= 0.5e9 and not r["prev_big_sell"]   # bot buys WITHOUT a dump just before
SC = {k[2:]: v for k, v in globals().items() if k.startswith("f_")}
TAB = {"D6": f"{RW}/tabN", "D7": f"{RW}/tabN", "D7b": "/home/moiz/sniper-data/wave37/tab"}
G = {}


def evfile(t):
    if t == "D7b": return f"{D}/ev_D7b.pkl"
    return f"{RW}/ev_{t}.pkl"


def comp_rows(t):
    if t in ("D6", "D7"): return pickle.load(open(f"{D}/comp_buys_N.pkl", "rb"))
    if t == "D7b": return pickle.load(open(f"{D}/comp_buys_r37.pkl", "rb"))
    return pickle.load(open(f"{D}/comp_buys_{t}.pkl", "rb"))


def windows(rows, Z, tp, scen):
    good = set(Z["hours"]); a, b = Z["a"], Z["b"]
    t2s = collections.defaultdict(list)
    for x in Z["T2"]: t2s[x["mint"]].append(x["slot"])
    bym = collections.defaultdict(list)
    for r in rows: bym[r["mint"]].append(r)
    out = []
    for m, rs in bym.items():
        c0 = tp.creates.get(m)
        if not c0 or not c0.get("v2") or c0.get("cashback"): continue
        rs.sort(key=lambda r: (r["slot"], r["idx"]))
        for q, r in enumerate(rs):
            if not (a <= r["bt"] < b and (r["bt"] // 3600) * 3600 in good): continue
            if r["age_slots"] is None or r["age_slots"] < 2 or r["vsol"] >= 100e9: continue
            ctx = dict(after_t2=any(s + 10 < r["slot"] <= s + 40 for s in t2s.get(m, ())),
                       swarm=len({x["who"] for x in rs[:q + 1] if x["slot"] >= r["slot"] - 2}) >= 2)
            if not SC[scen](r, ctx): continue
            out.append(dict(kind="re", mint=m, slot=r["slot"], idx=r["idx"], j=r["j"] + 1, en=r["slot"] + 10, whale_sell=None, k=8,
                            src=(r["who"], r["sol"]), age_slots=r["age_slots"], bt=r["bt"], create_slot=r["slot"] - r["age_slots"]))
    return out


def job(a):
    name, d = a
    XC = dict(G["XC"]); XC["sent"] = collections.Counter(); XC["refused"] = collections.Counter()
    res = wsim2.run_x(G["ck"], G["store"], G["T2"] + G["REW"][name], G["cfg"], G["land"], G["model"], G["view"], 9100 + d, G["pm"], XC)
    rows = []
    for r in res:
        t = r["trig"]; x = dict(kind=t["kind"], mint=t["mint"], slot=t["slot"], bt=t["bt"], src=t.get("src"), armed=r["armed"], why=r["why"])
        if r["armed"]:
            x.update(filled=r["filled"], nfail=r["nfail"], sent=r["sent"])
            if r["filled"]: x.update(fill_S=r["fill_S"], base=r["base"], grid=r["grid"])
        rows.append(x)
    return name, d, rows, sum(XC["sent"].values()), sum(XC["refused"].values())


if __name__ == "__main__":

    ap = argparse.ArgumentParser()
    ap.add_argument("day"); ap.add_argument("--draws", type=int, default=6); ap.add_argument("--scen", default="base," + ",".join(SC))
    ap.add_argument("--procs", type=int, default=7); ap.add_argument("--size", type=float, default=0.696)
    A = ap.parse_args(); t0 = time.time()
    Z = pickle.load(open(evfile(A.day), "rb"))
    tab = TAB.get(A.day, f"{D}/tabs/tab_{A.day}")
    T2 = [x for x in Z["T2"] if not x["q"]["all4"]]
    tp = rlib.Tape(tab=tab, with_ours=False)
    idm = tp.id_map(); our_ids = {idm[w] for w in OUR if w in idm}
    tp.drop_users = our_ids
    rows = comp_rows(A.day)
    scen = A.scen.split(",")
    REW = {"base": []}
    for s in scen:
        if s != "base": REW[s] = windows(rows, Z, tp, s)
    ck = tp.clock()
    allw = list(T2) + [x for v in REW.values() for x in v]
    sp = {}
    for x in allw:
        lo = x["create_slot"]; hi = (x["en"] if x["kind"] == "re" else x["slot"] + 10) + 70
        p, q = sp.get(x["mint"], (1 << 62, 0)); sp[x["mint"]] = (min(p, lo), max(q, hi))
    store = sim.LazyStore(tp, sp, maxn=6000)
    D3 = pickle.load(open(f"{s48lib.S48}/donors123.pkl", "rb"))
    pm = dsim.PathModel(); nm = drun.near_map()
    land = dsim.LandingX(D3, pm, nm, probes=("P3",)); model = s48lib.ModelN(D3, drun.s48_clock(), ("P1", "P2", "P3")); view = sim.View()

    import importlib.util
    spec = importlib.util.spec_from_file_location("r2run", "/home/moiz/sniper/ops/strategies/presend/rearm2/run.py"); r2 = importlib.util.module_from_spec(spec); spec.loader.exec_module(r2)
    cfg = r2.make_cfg(A.size, 0.20); cfg.sl = 0.50; cfg.cost = sim.Cost(fail_fee=5120)
    SD = pickle.load(open(f"{RW}/sell_delta.pkl", "rb"))
    dsell = [x for r in ("f28", "a34", "a35") for x in SD[r].get("time-ms", [])]
    grid = [(int(A.size * 1e9), 0.20, c) for c in (0.0, 0.2)]
    G.update(ck=ck, store=store, T2=T2, REW=REW, cfg=cfg, land=land, model=model, view=view, pm=pm, XC=dict(dsell=dsell, grid=grid, our_ids=our_ids))
    print(f"{A.day}: T2 armable {len(T2):,}; extra windows " + ", ".join(f"{k} {len(v):,}" for k, v in REW.items() if k != "base") + f"; setup {time.time()-t0:.0f} s", flush=True)
    out = collections.defaultdict(dict)
    with Pool(A.procs) as p:
        for name, d, rr, sent, ref in p.imap_unordered(job, [(s, d) for s in scen for d in range(A.draws)]):
            out[name][d] = dict(rows=rr, sent=sent, refused=ref)
            print(f"  {name} d{d}: fills {sum(1 for r in rr if r.get('filled'))} (extra {sum(1 for r in rr if r.get('filled') and r['kind']=='re')}) sent {sent} ref {ref} {time.time()-t0:.0f} s", flush=True)
    pickle.dump(dict(meta=dict(day=A.day, hours=Z["hours"], size=A.size, n={k: len(v) for k, v in REW.items()}), out=dict(out)), open(f"{D}/res_{A.day}.pkl", "wb"))
    print(f"{A.day}: done {time.time()-t0:.0f} s", flush=True)
