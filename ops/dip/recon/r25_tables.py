#!/usr/bin/env python3
# r25: the trade-by-trade table (every live attempt) for the report + summary numbers on fails ("what did being late cost").
# Columns: time PKT, server/run, token, size, leader client, measured landing (block-ms, slots after dump), trades ahead,
# live result + chain P&L, replay at our landing (old model, corrected model), replay at 35 / 50 ms, fill decomposition.
import sys, os, json, csv, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib as R

P = json.load(open(f"{R.WORK}/pertrade.json")); C = json.load(open(f"{R.WORK}/corrected_pertrade.json"))
RT = json.load(open(f"{R.WORK}/realtime.json"))["per"]
assert len(C) == len(P) == len(RT)
FAIL = 0.0005
def xold(o): return o["x_paper"]["pnl"] if o["x_st"] == 0 else (-FAIL if o["x_st"] == 1 else 0.0)
rows = []
for o, c, rt in zip(P, C, RT):
    d = o.get("decomp") or {}
    cl = (o["client"] or "?").replace("Agave", "").replace("Firedancer", "FD").replace("Labs", "")
    rows.append(dict(time=R.pkt(o["t_fire"], "%m-%d %H:%M:%S"), srv=o["srv"], run=o["run"], token=o["mint"][:6], size=o["size"], dev=int(bool(o["dev"])),
                     client=cl, L_block=round(o["L_meas"], 1), feed_ms=round(rt["feed_ms"], 1), slots_after=o["slots_after"], ahead=o["x_ahead"],
                     live=("fill" if o["live_fill"] else "fail"), live_pnl=round(o["chain_pnl"], 4), exit_live=o.get("exit_why_live") or "",
                     model_old=round(xold(o), 4), model_corr=round(c["corr"], 4),
                     at35=round(o["lat"]["35"]["pnl"], 4), at35_st=o["lat"]["35"]["st"], at50=round(o["lat"]["50"]["pnl"], 4), at50_st=o["lat"]["50"]["st"],
                     at0=round(o["lat"]["0"]["pnl"], 4),
                     d_entry=round(d.get("entry", 0), 4) if d else "", d_exit=round(d.get("exit", 0), 4) if d else "",
                     d_tape=round(d.get("tape", 0), 4) if d else "", d_costs=round(d.get("costs", 0), 4) if d else ""))
with open(f"{R.WORK}/pertrade_table.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
# ---- fails: what being late cost
fails = [(o, r) for o, r in zip(P, rows) if not o["live_fill"]]
for L in ("35", "50", "20", "0"):
    fl = [o for o, r in fails if o["lat"][L]["st"] == 0]
    print(f"live-failed buys {len(fails)}: replay at {L} ms would FILL {len(fl)}, worth {sum(o['lat'][L]['pnl'] for o in fl):+.3f} SOL "
          f"(all fails at {L} ms incl. guard fails: {sum(o['lat'][L]['pnl'] for o, r in fails):+.3f})")
fills = [o for o in P if o["live_fill"]]
print(f"live fills {len(fills)}: replay at 35 ms {sum(o['lat']['35']['pnl'] for o in fills):+.3f}, at our landing (old) {sum(xold(o) for o in fills):+.3f}, live {sum(o['chain_pnl'] for o in fills):+.3f}")
# ---- markdown appendix (compact)
md = ["| # | Time | Srv r | Token | SOL | Leader | Land ms (blk / feed) | Ahead | Live | Live P&L | Model@ours | @35 | @50 |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
for n, r in enumerate(rows, 1):
    s35 = r["at35"] if r["at35_st"] == 0 else ("fail" if r["at35_st"] == 1 else "n/a")
    s50 = r["at50"] if r["at50_st"] == 0 else ("fail" if r["at50_st"] == 1 else "n/a")
    md.append(f"| {n} | {r['time'][6:]} | {r['srv'][0]}{r['run']} | {r['token']} | {r['size']:.2f} | {r['client']} | {r['L_block']:.0f} / {r['feed_ms']:.0f} | {r['ahead']} | "
              f"{r['live']}{(' ' + r['exit_live'][:4]) if r['exit_live'] else ''} | {r['live_pnl']:+.4f} | {r['model_corr']:+.4f} | "
              f"{s35 if isinstance(s35, str) else format(s35, '+.4f')} | {s50 if isinstance(s50, str) else format(s50, '+.4f')} |")
open(f"{R.WORK}/pertrade_table.md", "w").write("\n".join(md) + "\n")
print(f"wrote {R.WORK}/pertrade_table.csv and .md ({len(rows)} rows)")
