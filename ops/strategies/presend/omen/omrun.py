#!/usr/bin/env python3
"""OMEN day replay (offline, INFERRED): rearm2's engine-faithful pre-send replay (omsim = wsim2 + OMEN window placement) with the live
AMS r35 settings (0.65 SOL, TP 20%, SL 20%, 0.88 limit, k 8, 40/s caps, QUIET skip + stop 6:2, one position, 200 ms exit MEASURED),
base (today's 6% rule) and OMEN variants, N draws with common random numbers.
usage: omrun.py DAY --draws N --vars spec.json --tag t [--procs 14]"""
import sys, os, pickle, time, argparse, collections, math, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.path.insert(0, "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/rearm2/code")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/density")
import rlib, sim, dsim, drun, s48lib, omsim
from run import make_cfg, OUR
from multiprocessing import Pool
W = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/omen"
R2 = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/rearm2"
SMS = rlib.SMS
GRID = [(650_000_000, 0.2, 0.0), (650_000_000, 0.2, 0.2), (450_000_000, 0.2, 0.0)]
G = {}


def quiet(x): return x["q"] is not None and x["q"]["all4"]


def predict(x, th):
    """OMEN: the wallet's learned habit predicts its dump in the next K slots -> predicted dump slot, else None"""
    f = x["om"]
    if f["n"] < th["N"] or f.get("pbig30", 0) < th["q"] or f.get("iqr", 999) > th["I"]: return None
    med = f.get("med", 999)
    if not (1 <= med <= th["K"]): return None
    return int(f["pos_s"] + round(med))


def place(x, ps, M, tag):
    st = max(x["slot"], ps - M); en = ps + M
    if en < x["slot"] + 1: return None
    y = dict(x); y["en"] = en; y["arm_ms"] = st * SMS if st > x["slot"] else 0.0; y["tag"] = tag
    return y


def build(TR, v):
    """v: dict(mode=base|A|Askip|Atime|B|C, X, N, q, I, M, K)"""
    base = [x for x in TR if x["floor"] == 3 and x["pct"] >= 6.0 and not quiet(x)]
    out = []
    mode = v["mode"]
    for x in base:
        if mode in ("base", "B"): out.append(dict(x, tag="b")); continue
        ps = predict(x, v); known = x["om"]["n"] >= v["N"]
        if ps is not None and mode in ("A", "Atime", "C"):
            y = place(x, ps, v["M"], "a_time")
            out.append(y if y is not None else dict(x, tag="b")); continue
        if ps is None and known and mode in ("A", "Askip", "C"): continue      # known wallet, no dump predicted: don't arm
        out.append(dict(x, tag="b"))
    if mode in ("B", "C"):
        X = v["X"]; fl = 2 if X < 3 else 3
        seen = {(x["mint"], x["whale_id"]) for x in base}
        for x in TR:
            if x["floor"] != fl or not (X <= x["pct"] < 6.0) or quiet(x) or x["age_slots"] == 0: continue
            if (x["mint"], x["whale_id"]) in seen: continue
            ps = predict(x, v)
            if ps is None: continue
            y = place(x, ps, v["M"], "add")
            if y is not None: out.append(y)
    return out


def spans(ws):
    sp = {}
    for x in ws:
        lo = x["create_slot"]; hi = max(x.get("en") or 0, x["slot"] + 10) + 70
        a, b = sp.get(x["mint"], (1 << 62, 0)); sp[x["mint"]] = (min(a, lo), max(b, hi))
    return sp


def row(r):
    t = r["trig"]
    d = dict(tag=t["tag"], mint=t["mint"], slot=t["slot"], bt=t["bt"], pct=t["pct"], armed=r["armed"], why=r["why"])
    if r["armed"]:
        d.update(filled=r["filled"], nfail=r["nfail"], sent=r["sent"], rate=r["rate"])
        if r["filled"]:
            d.update(grid=r["grid"], fill_S=r["fill_S"], why_exit=r["base"]["why"])
    return d


def job(a):
    name, d = a
    XC = dict(G["XC"]); XC["sent"] = collections.Counter(); XC["refused"] = collections.Counter()
    res = omsim.run_x(G["ck"], G["store"], G["WIN"][name], G["cfg"], G["land"], G["model"], G["view"], 9100 + d, G["pm"], XC)
    return name, d, [row(r) for r in res], dict(XC["sent"]), dict(XC["refused"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("day", type=int); ap.add_argument("--draws", type=int, default=10); ap.add_argument("--vars", required=True)
    ap.add_argument("--procs", type=int, default=14); ap.add_argument("--tag", default="main")
    A = ap.parse_args()
    t0 = time.time()
    Z = pickle.load(open(f"{W}/trig_D{A.day}.pkl", "rb")); TR = Z["TR"]
    for x in TR: x.pop("k", None); x.pop("mid", None)        # 'k' would be read as tries per slot by the simulator
    VS = json.load(open(A.vars)); VS = {"base": dict(mode="base"), **VS}
    WIN = {k: build(TR, v) for k, v in VS.items()}
    tp = rlib.Tape(tab=Z["tab"], with_ours=False)
    idm = tp.id_map(); our_ids = {idm[w] for w in OUR if w in idm}
    tp.drop_users = our_ids
    ck = tp.clock()
    allw = [x for v in WIN.values() for x in v]
    store = sim.LazyStore(tp, spans(allw), maxn=6000)
    D3 = pickle.load(open(f"{s48lib.S48}/donors123.pkl", "rb"))
    pm = dsim.PathModel(); nm = drun.near_map()
    land = dsim.LandingX(D3, pm, nm, probes=("P3",)); model = s48lib.ModelN(D3, drun.s48_clock(), ("P1", "P2", "P3")); view = sim.View()
    cfg = make_cfg(0.65, 0.2)
    SD = pickle.load(open(f"{R2}/sell_delta.pkl", "rb"))
    dsell = [x for r in ("f28", "a34", "a35") for x in SD[r].get("time-ms", [])]
    G.update(ck=ck, store=store, WIN=WIN, cfg=cfg, land=land, model=model, view=view, pm=pm, XC=dict(dsell=dsell, grid=GRID, our_ids=our_ids))
    print(f"D{A.day}: windows " + ", ".join(f"{k} {len(v):,}" for k, v in WIN.items()) + f"; setup {time.time() - t0:.0f} s", flush=True)
    jobs = [(s, d) for s in WIN for d in range(A.draws)]
    out = collections.defaultdict(dict)
    with Pool(A.procs) as p:
        for name, d, rows, sent, ref in p.imap_unordered(job, jobs):
            out[name][d] = dict(rows=rows, sent=sent, refused=ref)
    meta = dict(day=A.day, hours=Z["hours"], a=Z["a"], b=Z["b"], vars=VS)
    pickle.dump(dict(meta=meta, out=dict(out)), open(f"{W}/res_D{A.day}_{A.tag}.pkl", "wb"))
    print(f"D{A.day}: done {time.time() - t0:.0f} s", flush=True)
