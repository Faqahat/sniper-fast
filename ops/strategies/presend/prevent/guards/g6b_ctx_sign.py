#!/usr/bin/env python3
"""GUARDS step 6b: the pre-registered SIGN-TIME version of the context limit on the custom37 replay: each try's limit = 1 - D (D = 0.15 or
0.18) when, at that try's send time, a wallet other than the whale (and ours) holds >= 6% of supply (full token history, glib), else 0.12.
Same replay / config / rows as g4 (base vs variant, -20% followers).
usage: g6b_ctx_sign.py RUN D REPS OUT.json"""
import sys, json, bisect
import numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/custom37")
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/prevent/guards")
import c37lib as L
import glib as G
run, Dp, reps, outp = sys.argv[1], float(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
X, wins, R = L.load(run)
tapes = G.load_tapes({P.mint for P in wins})
HOLD = {m: G.Hold(r) for m, r in tapes.items()}
cache = {}
def other6(P, t_send):
    H = HOLD.get(P.mint)
    if H is None: return False
    k = bisect.bisect_left(P.c, t_send - P.off)
    if k > 0: y = P.out[k - 1]; KS = H.key(y[0], y[1], y[2]) + 1
    else: KS = H.key(P.s0, P.i0, 63)
    ck = (id(P), KS)
    v = cache.get(ck)
    if v is None:
        v = any(u != P.whale for u in H.holders_before(KS, 0.06)); cache[ck] = v
    return v

real_sb, real_lmo, real_ph = L.state_before, L.limit_min_out, L._phantoms
cur = {}; tried = {}; ON = [False]
def sb(P_, s, i):
    cur["x"] = tried.get((id(P_), s, i)); cur["P"] = P_
    return real_sb(P_, s, i)
def lmo(vsol, vtok, spend, fr, drop):
    if ON[0] and cur.get("x") is not None:
        drop = Dp if other6(cur["P"], cur["x"]["t"]) else 0.12
    return real_lmo(vsol, vtok, spend, fr, drop)
def ph(P, *a, **k):
    out = real_ph(P, *a, **k)
    for x in out:
        if x["land"] is not None: tried[(id(P), x["land"][0], x["land"][1])] = x
    return out
L.state_before = sb; L.limit_min_out = lmo; L._phantoms = ph
for P in wins:
    for tr in P.tries:
        if tr["land"] is not None: tried[(id(P), tr["land"][0], tr["land"][1])] = tr
out = {"run": run, "D": Dp, "reps": reps, "base": [], "guard": [], "base_cut": [], "guard_cut": []}
for rep in range(reps):
    for tag, cfg, on in (("base", L.BASE, False), ("guard", dict(L.BASE, drop=0.12 + 1e-9), True), ("base_cut", dict(L.BASE, cut=0.2), False),
                         ("guard_cut", dict(L.BASE, cut=0.2, drop=0.12 + 1e-9), True)):
        ON[0] = on
        r = L.run_sim(wins, R, cfg, rep)
        rows = []
        for P in wins:
            x = r[id(P)]; hour = int(((P.t_trig / 1e3) + 5 * 3600) // 3600 % 24)
            rows.append((P.W["ses"], P.W["w"], hour, bool(x["filled"]), x["pnl"] / 1e9))
        out[tag].append(rows)
    print(run, Dp, "rep", rep, {k: round(sum(r[4] for r in out[k][-1]), 3) for k in ("base", "guard", "base_cut", "guard_cut")},
          "fills", sum(r[3] for r in out["base"][-1]), "->", sum(r[3] for r in out["guard"][-1]), flush=True)
json.dump(out, open(outp, "w"))
