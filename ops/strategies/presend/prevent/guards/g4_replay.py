#!/usr/bin/env python3
"""GUARDS step 4: the custom37 PAIRED try-level replay (c37lib; real tries at their real landing positions, phantom tries only where the
live window had none: INFERRED) of T2 windows with a guard evaluated at each filling try's landing position:
  A_Z      the whale's balance at landing <= Z x its trigger balance (trigger balance from the engine's arm record + the whale's trades
           on the tape after the trigger)
  B6a1     the largest wallet holding >= 6% at the try's send time (full token history, glib) must hold < 6% at landing
Closing treatment: OPEN (accounts never closed) or NAIVE (a guarded wallet that sold out between signing and landing closed its account
with p 0.39 -> the try fails). Config = custom37 BASE (the r37 config, 0.696 SOL) for every run, as custom37. Rows: baseline vs guard,
same reps (worlds); also the -20% followers row (cfg cut 0.2).
usage: g4_replay.py RUN VARIANT TRT REPS OUT.json"""
import sys, json, math, bisect, pickle
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/custom37")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/prevent/guards")
import c37lib as L
import glib as G
PCLOSE = 0.39
run, var, trt, reps, outp = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5]
X, wins, R = L.load(run)
HOLD = {}
if var.startswith("B"):
    tapes = G.load_tapes({P.mint for P in wins})
    HOLD = {m: G.Hold(r) for m, r in tapes.items()}

# per window: the whale's trades after the trigger (block-clock order) for guard A
for P in wins:
    P.wh_keys = []; P.wh_bal = []
    b = float(P.W["trig"].get("bal") or 0)
    P.trig_bal = b
    for x in P.out:
        if x[6] == P.whale:
            b += x[5] if x[3] else -x[5]
            P.wh_keys.append(x[0] * 100000 + x[1]); P.wh_bal.append(b)


def wbal(P, s, i):
    k = bisect.bisect_left(P.wh_keys, s * 100000 + i)
    return P.wh_bal[k - 1] if k > 0 else P.trig_bal


def guard_ok(P, x, s, i, rng):
    if var == "none": return True
    t_sign = x["t"]
    if var.startswith("A"):
        Z = float(var.split("_")[1])
        if P.trig_bal <= 0: return True
        bl = wbal(P, s, i)
        if bl > Z * P.trig_bal: return False
        if trt == "naive" and bl <= 0:
            # sold out: was it still holding at signing? (signing = trades with block clock < send time - off)
            k = bisect.bisect_left(P.c, t_sign - P.off)
            ks = P.out[k - 1][0] * 100000 + P.out[k - 1][1] if k > 0 else 0
            bs = wbal(P, P.out[k - 1][0], P.out[k - 1][1] + 1) if k > 0 else P.trig_bal
            if bs > 0 and rng.random() < PCLOSE: return False
        return True
    H = HOLD.get(P.mint)
    if H is None: return True
    k = bisect.bisect_left(P.c, t_sign - P.off)
    if k > 0:
        y = P.out[k - 1]; KS = H.key(y[0], y[1], y[2]) + 1
    else:
        KS = H.key(P.s0, P.i0, 63)
    hs = H.holders_before(KS, 0.06)
    if not hs: return True
    u, bS = max(hs.items(), key=lambda kv: kv[1])
    bL = H.bal_before(u, H.key(s, i, 0))
    if bL >= 0.06 * G.SUP: return False
    if trt == "naive" and bL <= 0 and rng.random() < PCLOSE: return False
    return True


_orig = L.window_sim
def window_sim_g(P, cfg, R, rng, pause_cf=(), gaps_live=()):
    """c37lib.window_sim with the guard: same code path, the fill test gets guard_ok (see c37lib for everything else)"""
    if var == "none": return _orig(P, cfg, R, rng, pause_cf, gaps_live)
    # wrap state_before so that a try failing the guard never fills: simplest exact way = filter candidate tries by re-running the
    # first-fill search here, then hand c37lib the same try list minus the blocked ones (their landed fee still counts)
    blocked = set()
    grng = np.random.default_rng([rep_now[0], P.W["ses"], P.W["w"], 99])
    size = int(round(cfg["size"] * 1e9))
    def is_fill(x):
        s, i = x["land"]
        if s > x["dl"]: return False
        V, T, kn = L.state_before(P, s, i)
        mo = x.get("min_out_live")
        if mo is None: mo, _ = L.limit_min_out(x["vsol"], x["vtok"], size, L.FR, L.window_drop(P, cfg))
        tok, _ = L.buy_out(V, T, size)
        return tok >= mo
    # c37lib builds the try list inside window_sim; we patch L.buy_out during this call so a blocked landing returns 0 tokens
    real_buy_out = L.buy_out
    cur = {}
    def buy_out_g(V, T, spend, fr=L.FR):
        r = real_buy_out(V, T, spend, fr)
        x = cur.get("x")
        if x is not None and not guard_ok(P, x, x["land"][0], x["land"][1], grng): return (0, r[1])
        return r
    # c37lib.window_sim calls state_before(P, s, i) then limit_min_out then buy_out for each landed try in order: hook state_before to
    # remember which try is being tested (by its landing)
    real_state_before = L.state_before
    tried = {}
    def state_before_g(P_, s, i):
        cur["x"] = tried.get((s, i))
        return real_state_before(P_, s, i)
    # map landing -> try: c37lib passes tries in its own list; we cannot see it, so recover by intercepting limit_min_out? Simpler: the
    # landing (s, i) of a try is unique enough per window (two tries landing in the same tx index is impossible).
    L.state_before = state_before_g; L.buy_out = buy_out_g
    try:
        # pre-register every real try's landing; phantom tries are registered by the wrapped _phantoms
        for tr in P.tries:
            if tr["land"] is not None: tried[tuple(tr["land"])] = tr
        real_ph = L._phantoms
        def ph_g(*a, **k):
            out = real_ph(*a, **k)
            for x in out:
                if x["land"] is not None: tried[tuple(x["land"])] = x
            return out
        L._phantoms = ph_g
        res = _orig(P, cfg, R, rng, pause_cf, gaps_live)
    finally:
        L.state_before = real_state_before; L.buy_out = real_buy_out; L._phantoms = real_ph
    return res


rep_now = [0]
L.window_sim = window_sim_g
out = {"run": run, "var": var, "trt": trt, "reps": reps, "base": [], "guard": [], "base_cut": [], "guard_cut": []}
for rep in range(reps):
    rep_now[0] = rep
    for tag, cfg, g in (("base", L.BASE, "none"), ("guard", L.BASE, var), ("base_cut", dict(L.BASE, cut=0.2), "none"), ("guard_cut", dict(L.BASE, cut=0.2), var)):
        var_save = var
        globals()["var"] = g
        r = L.run_sim(wins, R, cfg, rep)
        globals()["var"] = var_save
        rows = []
        for P in wins:
            x = r[id(P)]
            hour = int(((P.t_trig / 1e3) + 5 * 3600) // 3600 % 24)
            rows.append((P.W["ses"], P.W["w"], hour, bool(x["filled"]), x["pnl"] / 1e9, x.get("live_try", False), x.get("src")))
        out[tag].append(rows)
    print(run, var, trt, "rep", rep, {k: round(sum(r[4] for r in out[k][-1]), 3) for k in ("base", "guard", "base_cut", "guard_cut")},
          "fills", sum(r[3] for r in out["base"][-1]), "->", sum(r[3] for r in out["guard"][-1]), flush=True)
json.dump(out, open(outp, "w"))
