#!/usr/bin/env python3
# r21: per run, corrected model at our EXACT landing: the run's own exit vs hold 5 (no SL / SL 20%) vs hold 6 SL 10%; live for reference.
import sys, os, json, collections
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
acc = collections.defaultdict(lambda: np.zeros(6))
for o in P:
    k = (o["srv"], o["run"]); cfg = runs[k]["cfg"]; sl = cfg["sl"] if cfg["sl"] < 0.5 else None
    TP = TPS[o["tape"]]; t, j0 = TP.find(o["mint"], o["dump_slot"], o["dump_idx"], o.get("sell")); tp = TP.token(t)
    rx = S.run_path(tp, j0, o["size"], at=(o["land_slot"], o["land_idx"]))
    rx35 = S.run_path(tp, j0, 0.35, at=(o["land_slot"], o["land_idx"]))
    v = [o["chain_pnl"], outcome(rx, cfg["hold_slots"], sl, cost[k], fcost[k])["pnl"], outcome(rx, 5, None, cost[k], fcost[k])["pnl"],
         outcome(rx, 5, 0.2, cost[k], fcost[k])["pnl"], outcome(rx, 6, 0.1, cost[k], fcost[k])["pnl"], outcome(rx35, cfg["hold_slots"], sl, cost[k], fcost[k])["pnl"]]
    acc[k] += v; acc[("ALL", 0)] += v
print(f"{'run':9s} {'live':>7s} {'as run':>7s} {'h5 noSL':>8s} {'h5 SL20':>8s} {'h6 SL10':>8s} {'as run @0.35 SOL':>16s}")
for k in sorted(acc, key=str):
    a = acc[k]; print(f"{k[0]} r{k[1]:<3d}  {a[0]:+7.3f} {a[1]:+7.3f} {a[2]:+8.3f} {a[3]:+8.3f} {a[4]:+8.3f} {a[5]:+16.3f}")
