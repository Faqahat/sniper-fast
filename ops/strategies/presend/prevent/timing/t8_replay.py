#!/usr/bin/env python3
"""TIMING step 8: custom37 PAIRED try-level replay (c37lib, r37 config, 0.696 SOL; GUARDS g4 hook pattern) of
  a2_X{X}_t{tau}  a try cannot fill if a wallet holding >= X% at the try's SIGNING (last trade seen) with timer hazard hz(3) >= tau
                  (online, at the send slot) still holds >= X% at the try's landing  (OPEN: accounts never closed)
  b2_t{tau}       same, only the T2 whale, still holding >= 50% of its trigger balance at landing
  c_X{X}_t{tau}   EARLY SELL: at our fill, a wallet holding >= X% just before our buy with hz(2) >= tau -> exit_ms 0 (sell at fill seen)
Blocked tries keep their landed fee (conservative). Rows per rep: base, base_cut (-20% followers), and per variant v, v_cut.
usage: t8_replay.py RUN REPS OUT.json VARIANT [VARIANT ...]"""
import sys, json, bisect
import numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/custom37")
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/prevent/guards")
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/prevent/timing")
import c37lib as L
import glib as G
import tlib as T
run, reps, outp, VARS = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4:]
X_, wins, R = L.load(run)
tapes = G.load_tapes({P.mint for P in wins})
HOLD = {m: G.Hold(r) for m, r in tapes.items()}
FIRST = {m: {u: ks[0] >> 24 for u, (ks, bs) in H.tl.items()} for m, H in HOLD.items()}
for P in wins: P.trig_bal = float(P.W["trig"].get("bal") or 0)
cur = {"var": "none"}


def parse(v):
    if v.startswith("a2_"): _, x, t = v.split("_"); return ("a2", float(x[1:]), float(t[1:]))
    if v.startswith("b2_"): _, t = v.split("_"); return ("b2", 6.0, float(t[1:]))
    if v.startswith("c_"): _, x, t = v.split("_"); return ("c", float(x[1:]), float(t[1:]))
    return ("none", 0, 0)


def sign_key(P, x):
    H = HOLD.get(P.mint)
    k = bisect.bisect_left(P.c, x["t"] - P.off)
    if k > 0:
        y = P.out[k - 1]; return H.key(y[0], y[1], y[2]) + 1
    return H.key(P.s0, P.i0, 63)


def blocked(P, x, s, i):
    kind, X, tau = parse(cur["var"])
    if kind not in ("a2", "b2"): return False
    H = HOLD.get(P.mint)
    if H is None: return False
    KS = sign_key(P, x); S = int(x["slot"])
    hs = H.holders_before(KS, X / 100.0)
    for u, b in hs.items():
        if kind == "b2" and u != P.whale: continue
        fs = FIRST[P.mint].get(u)
        if fs is None: continue
        p, n = T.hz(u, S, P.mint, S - fs, 3)
        if p is None or p < tau: continue
        bl = H.bal_before(u, H.key(s, i, 0))
        thr = 0.5 * P.trig_bal if kind == "b2" else X / 100.0 * G.SUP
        if bl >= thr: return True
    return False


_orig_ws = L.window_sim; _orig_ex = L.exit_walk
real_state_before = L.state_before; real_buy_out = L.buy_out; real_ph = L._phantoms


def window_sim_g(P, cfg, R_, rng, pause_cf=(), gaps_live=()):
    kind = parse(cur["var"])[0]
    if kind not in ("a2", "b2"): return _orig_ws(P, cfg, R_, rng, pause_cf, gaps_live)
    tried = {}; cx = {}
    for tr in P.tries:
        if tr["land"] is not None: tried[tuple(tr["land"])] = tr
    def ph_g(*a, **k):
        out = real_ph(*a, **k)
        for x in out:
            if x["land"] is not None: tried[tuple(x["land"])] = x
        return out
    def sb_g(P_, s, i):
        cx["x"] = tried.get((s, i)); cx["si"] = (s, i)
        return real_state_before(P_, s, i)
    def bo_g(V, Tt, spend, fr=L.FR):
        r = real_buy_out(V, Tt, spend, fr)
        x = cx.get("x")
        if x is not None and blocked(P, x, *cx["si"]): return (0, r[1])
        return r
    L.state_before = sb_g; L.buy_out = bo_g; L._phantoms = ph_g
    try:
        return _orig_ws(P, cfg, R_, rng, pause_cf, gaps_live)
    finally:
        L.state_before = real_state_before; L.buy_out = real_buy_out; L._phantoms = real_ph


def exit_walk_g(P, kn, Tb, tok, size, t_fill, Dw, tau, cfg, R_, rng, live_fill_try, fs):
    kind, X, th = parse(cur["var"])
    if kind == "c":
        H = HOLD.get(P.mint)
        if H is not None:
            KS = H.key(P.out[kn - 1][0], P.out[kn - 1][1], P.out[kn - 1][2]) + 1 if kn > 0 else H.key(P.s0, P.i0, 63)
            for u, b in H.holders_before(KS, X / 100.0).items():
                f0 = FIRST[P.mint].get(u)
                if f0 is None: continue
                p, n = T.hz(u, int(fs), P.mint, int(fs) - f0, 2)
                if p is not None and p >= th:
                    cfg = dict(cfg, exit_ms=0); cur["early"] += 1; break
    return _orig_ex(P, kn, Tb, tok, size, t_fill, Dw, tau, cfg, R_, rng, live_fill_try, fs)


L.window_sim = window_sim_g; L.exit_walk = exit_walk_g
out = {"run": run, "reps": reps, "vars": VARS, "rows": {}}
for rep in range(reps):
    for v in ["none"] + VARS:
        for cut in (0.0, 0.2):
            cur["var"] = v; cur["early"] = 0
            r = L.run_sim(wins, R, dict(L.BASE, cut=cut), rep)
            rows = []
            for P in wins:
                x = r[id(P)]
                rows.append((P.W["ses"], P.W["w"], int(P.t_trig), bool(x["filled"]), x["pnl"] / 1e9, x.get("why")))
            out["rows"].setdefault(f"{v}|{cut}", []).append(rows)
            print(run, rep, v, cut, "pnl", round(sum(q[4] for q in rows), 3), "fills", sum(q[3] for q in rows), "early", cur["early"], flush=True)
json.dump(out, open(outp, "w"))
