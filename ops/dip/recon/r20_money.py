#!/usr/bin/env python3
# r20: where the live money went (chain): curve P&L of the fills, pump fees, tx fees, tips, failed buys -- per server and total.
# Plus the exit alternatives at our EXACT landings (corrected model): hold 3..19 slots, with / without the stop-loss.
import sys, os, json, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib as R, rsim as S
from r13_corrected import outcome
P = json.load(open(f"{R.WORK}/pertrade.json")); F = json.load(open(f"{R.WORK}/fires.json"))
runs = {(r["srv"], r["run"]): r for r in F["runs"]}; fr = {(r["srv"], r["mint"], r["dump_slot"]): r for r in F["rows"]}
acc = collections.defaultdict(lambda: collections.defaultdict(float))
for o in P:
    r = fr[(o["srv"], o["mint"], o["dump_slot"])]
    for g in (o["srv"], "ALL"):
        a = acc[g]
        if o["live_fill"]:
            sells = [s for s in r["sells"] if not s.get("missing")]
            ok = [s for s in sells if not s.get("err")]
            X = r["land_sol"] / 1e9; spend = o["size"]
            gross_out = sum(s["sol"] for s in ok) / 1e9; recv = o["sell_received"]
            a["fills"] += 1; a["curve"] += gross_out - X; a["pump_buy"] += spend - X; a["pump_sell"] += gross_out - recv
            a["buy_fee"] += (r.get("land_fee") or 0) / 1e9; a["buy_tip"] += (r.get("land_tips") or 0) / 1e9
            a["sell_fee"] += sum((s.get("fee") or 0) for s in sells) / 1e9; a["sell_tip"] += sum((s.get("tips") or 0) for s in sells) / 1e9
            a["chain_fills"] += o["chain_pnl"]
        else:
            a["fails"] += 1; a["fail_cost"] += o["chain_pnl"]
        a["chain"] += o["chain_pnl"]
print("LIVE money (SOL, chain):")
for g in ("FRA", "AMS", "ALL"):
    a = acc[g]
    rest = a["chain_fills"] - (a["curve"] - a["pump_buy"] - a["pump_sell"] - a["buy_fee"] - a["buy_tip"] - a["sell_fee"] - a["sell_tip"])
    print(f"  {g}: fills {int(a['fills'])}: curve {a['curve']:+.3f} | pump fees buy {-a['pump_buy']:.3f} sell {-a['pump_sell']:.3f} | tx fees buy {-a['buy_fee']:.3f} sell {-a['sell_fee']:.3f} "
          f"| tips buy {-a['buy_tip']:.3f} sell {-a['sell_tip']:.3f} | rest {rest:+.4f} | = fills {a['chain_fills']:+.3f}; failed buys {int(a['fails'])}: {a['fail_cost']:+.3f}; TOTAL {a['chain']:+.3f}")
json.dump({g: dict(v) for g, v in acc.items()}, open(f"{R.WORK}/money.json", "w"))
# ---- exit alternatives at our exact landing
TPS = {tag: S.Tapes(tag) for tag in ("NEW", "OLD")}
cost = {}; fcost = {}
for k in runs:
    fl = [o for o in P if (o["srv"], o["run"]) == k and o["live_fill"] and o.get("buy_txcost") is not None]
    fa = [o for o in P if (o["srv"], o["run"]) == k and not o["live_fill"]]
    cost[k] = float(np.mean([o["buy_txcost"] + o["sell_txcost"] for o in fl])) if fl else 0.0031
    fcost[k] = float(np.mean([-o["chain_pnl"] for o in fa])) if fa else 0.000505
print("\nexit alternatives on the same 309 fires (corrected model): at OUR EXACT landing | at 35 ms")
cache = []
for o in P:
    k = (o["srv"], o["run"]); TP = TPS[o["tape"]]; t, j0 = TP.find(o["mint"], o["dump_slot"], o["dump_idx"], o.get("sell")); tp = TP.token(t)
    cache.append((o, k, S.run_path(tp, j0, o["size"], at=(o["land_slot"], o["land_idx"])), S.run_path(tp, j0, o["size"], L=35.0)))
for hold in (3, 4, 5, 6, 8, 12, 19):
    for sl in (None, 0.10, 0.20):
        a = sum(outcome(rx, hold, sl, cost[k], fcost[k])["pnl"] for o, k, rx, r35 in cache)
        b = sum(outcome(r35, hold, sl, cost[k], fcost[k])["pnl"] for o, k, rx, r35 in cache)
        print(f"   hold {hold:2d} (sell slot +{hold - 1}) SL {'none' if sl is None else f'{int(sl * 100)}%':4s}: {a:+7.3f} | {b:+7.3f}")
