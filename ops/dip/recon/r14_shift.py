#!/usr/bin/env python3
# r14: speed what-ifs on the SAME 309 live fires with the corrected model:
#  - our exact landing (measured), and our landing moved earlier by 10/20/35/50 block-ms (same dump-by-dump pattern),
#  - fixed latency for every fire (0..150 ms), our median (58 ms) for every fire,
#  - shuffled: the measured latencies randomly re-assigned across fires (breaks any link between where we are slow and
#    which dumps pay) -> tests whether we are slow exactly on the dumps that pay.
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
items = []
for o in P:
    k = (o["srv"], o["run"]); cfg = runs[k]["cfg"]; sl = cfg["sl"] if cfg["sl"] < 0.5 else None
    TP = TPS[o["tape"]]; t, j0 = TP.find(o["mint"], o["dump_slot"], o["dump_idx"], o.get("sell")); tp = TP.token(t)
    items.append((o, k, cfg, sl, tp, j0))
def val(it, L=None, at=None):
    o, k, cfg, sl, tp, j0 = it
    res = S.run_path(tp, j0, o["size"], L=L, at=at)
    return outcome(res, cfg["hold_slots"], sl, cost[k], fcost[k])
Lm = np.array([it[0]["L_meas"] for it in items])
def row(name, ocs):
    p = sum(x["pnl"] for x in ocs); f = sum(x["st"] == 0 for x in ocs)
    print(f"  {name:44s} {p:+7.3f} SOL  fills {f:3d}/{len(ocs)}"); return p
print(f"same {len(items)} fires, corrected model (live = {sum(it[0]['chain_pnl'] for it in items):+.3f})")
out = {}
out["exact"] = row("our exact landing (measured)", [val(it, at=(it[0]["land_slot"], it[0]["land_idx"])) for it in items])
for d in (10, 20, 35, 50):
    out[f"shift{d}"] = row(f"measured landing moved {d} ms earlier", [val(it, L=max(0.0, float(it[0]["L_meas"]) - d)) for it in items])
out["asclock"] = row("measured landing as clock-ms (same L, check)", [val(it, L=float(it[0]["L_meas"]) + 1e-6) for it in items])
for L in (0, 10, 20, 35, 50, 58, 75, 100, 150):
    out[f"fix{L}"] = row(f"fixed {L} ms for every fire", [val(it, L=float(L)) for it in items])
rng = np.random.default_rng(3); sh = []
for rep in range(5):
    perm = rng.permutation(len(items))
    sh.append(sum(val(it, L=float(Lm[perm[i]]))["pnl"] for i, it in enumerate(items)))
print(f"  {'shuffled measured latencies (5 draws)':44s} {np.mean(sh):+7.3f} SOL  (draws {', '.join(f'{x:+.2f}' for x in sh)})")
out["shuffled"] = float(np.mean(sh))
json.dump(out, open(f"{R.WORK}/shift.json", "w"))
