#!/usr/bin/env python3
"""SL-REDFLAGS s3: print the SL table (every stop-loss exit) and the big-loss (< -0.08) non-SL list."""
import json, sys
from datetime import datetime, timezone, timedelta
PKT = timezone(timedelta(hours=5))
R = [json.loads(l) for l in open("/home/moiz/sniper-data/filters3/slflags/rows.jsonl")]
def ts(t): return datetime.fromtimestamp(t / 1e9, PKT).strftime("%m-%d %H:%M")
def f(x, n=1): return "-" if x is None else (f"{x:.{n}f}" if isinstance(x, (int, float)) else str(x))
sel = sys.argv[1] if len(sys.argv) > 1 else "sl"
for d in R:
    sl = d["exit"] in ("stop-loss", "sl")
    if sel == "sl" and not sl: continue
    if sel == "big" and (sl or d["pnl"] > -0.08): continue
    hs = sorted([h for h in d.get("holders") or []], key=lambda h: -h["pct"])[:5]
    print(f"r{d['run']} {ts(d['t'])} {d['kind']:5s} {d['pnl']:+.3f} {d['mint'][:6]} age {f(d['age'],0)} wh {f(d['w_pct'])}% whN {f(d.get('whale_n'),0)} "
          f"rem {f(d.get('whale_rem'),2)} n120 {f(d['n120'],0)} nb50 {f(d['nb50'],0)} whd {f(d['wh_dumps'],0)} sl {f(d['since_last'],0)} coh {f(d['coh_hold'],0)} "
          f"dd120 {f(d['dd120'],2)} vsol {f(d['trig_vsol'],0)} tsol {f(d['trig_sol'],1)} sat {d['sat']} depth {f((d['depth'] or 0)*100,0)}% "
          f"oth {f(d.get('sum_oth'),0)} fresh {f(d.get('sum_fresh'),0)} maxo {f(d.get('max_oth'),1)}(n{d.get('max_oth_n')},a{d.get('max_oth_age')}) "
          f"cr {str(d['creator'])[:6]} {f(d['cr_pct'],0)}%")
    print("     holders: " + "; ".join(f"{h['w'][:6]} {h['pct']:.1f}% a{h['age']} n{h['n']}" for h in hs))
    print("     sold-in: " + "; ".join(f"{u[:6]} {v}{'H' if hh else ''}" for u, v, hh in d["o_sells"][:5]) + f" | bought {d['o_bought']:.2f} ({d['o_nbuy']})")
