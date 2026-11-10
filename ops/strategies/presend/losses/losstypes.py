"""Loss typing of the biggest losers + per-type totals (MEASURED from live records and hold tapes)."""
import json, collections
from chainfeat import *
from exitsim import replay
from test_exit import big_sell
def typ(x):
    if x["trig_age"] is not None and x["trig_age"] < 2: return "A launch-slot whale (whale bought in slot create+1)"
    if x["hold_sell_sol"] >= 5: return "B sell cascade during hold (>=5 SOL of other sells before our sell)"
    if x["hold_max_sell"] >= 1: return "C second dumper (one other sell >=1 SOL before our sell)"
    if x["hold_sell_sol"] + x["hold_buy_sol"] == 0: return "D flat (nobody traded before our sell: fees+tip)"
    return "E small drift (small sells / no followers)"
allx = []
for run in RUNS:
    for r in load(run):
        x = dict(feats(r), run=run, mint=r["mint"]); c = cfeats(r) or {}; x.update(c); x["type"] = typ(x)
        x["bigsell1_delta"] = replay(r, big_sell(1.0))[0]
        allx.append(x)
json.dump(allx, open("/home/it/sniper-data/presend_losses/all_fills_features.json", "w"))
L = sorted([x for x in allx if x["pnl"] < 0], key=lambda x: x["pnl"])
top = L[:40]
print("TOP 40 losers:", round(sum(x["pnl"] for x in top), 3), "| all losers", len(L), round(sum(x["pnl"] for x in L), 3))
for grp, name in ((top, "top40"), (L, "all losers"), ([x for x in allx if x["pnl"] >= 0], "winners")):
    c = collections.defaultdict(lambda: [0, 0.0])
    for x in grp: c[x["type"]][0] += 1; c[x["type"]][1] += x["pnl"]
    print(name); [print(f"   {k}: n{v[0]} {v[1]:+.3f}") for k, v in sorted(c.items())]
print()
print("| # | run | token | P&L | type | whale buy SOL / % / token age (slots) | dump drop % / SOL | fill: slots after trigger, send->seen ms, client | hold: other sells before our sell (SOL, max), seen before 200 ms decision | QUIET q | link |")
for i, x in enumerate(top, 1):
    print(f"| {i} | {x['run']} | {x['mint'][:6]} | {x['pnl']:+.3f} | {x['type'][0]} | {x['trig_sol']:.2f} / {x['trig_pct']:.1f} / {x['trig_age']} | "
          f"{(x['drop'] or 0):.0f} / {(x['dump_sol'] or 0):.1f} | +{x['sat']}, {x['send_rx']:.0f}, {(x['client'] or '')[:8]} | {x['hold_sell_sol']:.1f}, {x['hold_max_sell']:.1f}; seen {x['seen_sell_sol']:.1f} | "
          f"{''.join('T' if b else 'f' for b in (x['q'] or []))} | [gmgn](https://gmgn.ai/sol/token/{x['mint']}) |")
