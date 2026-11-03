#!/usr/bin/env python3
"""GUARDS step 6: context-dependent limit / window rules and the stop-loss piece, on the custom37 paired replay (T2 windows; real tries at
real landings, phantoms INFERRED where the live window had none), r37 config for every run (as custom37).
Variants (holders = wallets but ours and the whale with >= 6% of supply at the trigger, full token history from glib tapes; arm-time only):
  d15_if_h1   drop 0.15 when >= 1 other 6% holder at the trigger, else 0.12
  d18_if_h1   drop 0.18 when >= 1 other 6% holder
  skip_if_h1  no window when >= 1 other 6% holder
  skip_if_h2  no window when >= 2 other 6% holders
  win5_if_h1  5-slot window when >= 1 other 6% holder
  sl_off      no stop-loss (200 ms timer, 2-slot backstop, TP 20% kept)
  sl_after1   stop-loss only on trades in a later slot than our fill
usage: g6_ctx_sl.py RUN REPS OUT.json"""
import sys, json, inspect, pickle
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/custom37")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/prevent/guards")
import c37lib as L
import glib as G
run, reps, outp = sys.argv[1], int(sys.argv[2]), sys.argv[3]
X, wins, R = L.load(run)
tapes = G.load_tapes({P.mint for P in wins})
for P in wins:
    rows = tapes.get(P.mint)
    if not rows: P.h6 = 0; continue
    H = G.Hold(rows); tg = P.W["trig"]
    hs = H.holders_before(H.key(tg["slot"], tg["idx"], tg.get("j", 0)) + 1, 0.06)
    P.h6 = sum(1 for u in hs if u != P.whale)

# SL after 1 slot: a copy of c37lib.exit_walk whose stop-loss needs the trade's slot > our fill slot
src = inspect.getsource(L.exit_walk)
old = 'h = "tp" if (tp is not None and v >= 1 + tp) else ("sl" if (sl is not None and v <= 1 - sl) else None)'
assert old in src
src2 = src.replace("def exit_walk(", "def exit_walk_sl1(").replace(old, 'h = "tp" if (tp is not None and v >= 1 + tp) else ("sl" if (sl is not None and v <= 1 - sl and x[0] > fs) else None)')
ns = {}; exec(src2, L.__dict__, ns); exit_walk_sl1 = ns["exit_walk_sl1"]
_ew = L.exit_walk

B = L.BASE
VARS = {
    "base": lambda P: B,
    "d15_if_h1": lambda P: dict(B, drop=0.15) if P.h6 >= 1 else B,
    "d18_if_h1": lambda P: dict(B, drop=0.18) if P.h6 >= 1 else B,
    "skip_if_h1": lambda P: None if P.h6 >= 1 else B,
    "skip_if_h2": lambda P: None if P.h6 >= 2 else B,
    "win5_if_h1": lambda P: dict(B, win=5) if P.h6 >= 1 else B,
    "sl_off": lambda P: dict(B, sl=None),
    "sl_after1": lambda P: dict(B, sl1=True),
}
out = {"run": run, "reps": reps, "h6": {f"{P.W['ses']}_{P.W['w']}": P.h6 for P in wins}, "rows": {}}
for name, f in VARS.items():
    for cut in (0.0, 0.2):
        tag = f"{name}|{cut}"; out["rows"][tag] = []
        for rep in range(reps):
            def cfg(P, f=f, cut=cut):
                c = f(P)
                return None if c is None else dict(c, cut=cut)
            if name == "sl_after1": L.exit_walk = exit_walk_sl1
            r = L.run_sim(wins, R, cfg, rep)
            L.exit_walk = _ew
            rows = []
            for P in wins:
                x = r[id(P)]
                hour = int(((P.t_trig / 1e3) + 5 * 3600) // 3600 % 24)
                rows.append((P.W["ses"], P.W["w"], hour, bool(x["filled"]), x["pnl"] / 1e9, x.get("why")))
            out["rows"][tag].append(rows)
        print(run, tag, [round(sum(r[4] for r in rr), 3) for rr in out["rows"][tag]], flush=True)
json.dump(out, open(outp, "w"))
