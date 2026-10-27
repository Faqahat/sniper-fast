#!/usr/bin/env python3
# r19: what the +5% guard did on the 309 live fires: corrected model at our EXACT landing with the guard at 5 / 10 / 15 / 20 / 30% /
# none; and at 35 ms. The failed buys (180) were all guard fails: what would they have made?
import sys, os, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib as R, rsim as S
from r13_corrected import outcome
P = json.load(open(f"{R.WORK}/pertrade.json")); runs = {(r["srv"], r["run"]): r for r in json.load(open(f"{R.WORK}/fires.json"))["runs"]}
TPS = {tag: S.Tapes(tag) for tag in ("NEW", "OLD")}
cost = {}; fcost = {}
for k in runs:
    fl = [o for o in P if (o["srv"], o["run"]) == k and o["live_fill"] and o.get("buy_txcost") is not None]
    fa = [o for o in P if (o["srv"], o["run"]) == k and not o["live_fill"]]
    cost[k] = float(np.mean([o["buy_txcost"] + o["sell_txcost"] for o in fl])) if fl else 0.0031
    fcost[k] = float(np.mean([-o["chain_pnl"] for o in fa])) if fa else 0.000505
print("corrected model, same 309 fires: SOL total (fills) | live-failed buys only")
for G in (1.05, 1.10, 1.15, 1.20, 1.30, 100.0):
    for mode in ("exact", "35"):
        tot = 0; nf = 0; tf = 0; nff = 0
        for o in P:
            k = (o["srv"], o["run"]); cfg = runs[k]["cfg"]; sl = cfg["sl"] if cfg["sl"] < 0.5 else None
            TP = TPS[o["tape"]]; t, j0 = TP.find(o["mint"], o["dump_slot"], o["dump_idx"], o.get("sell")); tp = TP.token(t)
            res = S.run_path(tp, j0, o["size"], at=(o["land_slot"], o["land_idx"])) if mode == "exact" else S.run_path(tp, j0, o["size"], L=35.0, guard=G)
            if mode == "exact": res = S.run_path(tp, j0, o["size"], at=(o["land_slot"], o["land_idx"]), guard=G)
            oc = outcome(res, cfg["hold_slots"], sl, cost[k], fcost[k])
            tot += oc["pnl"]; nf += oc["st"] == 0
            if not o["live_fill"]: tf += oc["pnl"]; nff += oc["st"] == 0
        print(f"  guard {'none' if G > 50 else f'+{round((G - 1) * 100)}%':5s} at {mode:5s}: {tot:+7.3f} ({nf} fills) | live-failed buys: {tf:+7.3f} ({nff} would fill)")
