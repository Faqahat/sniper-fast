#!/usr/bin/env python3
"""TUNE t1: reproduce the owner's r42 dashboard (filters_report.py rules, run-only bad-creator ledger), then split each filter by
period: DEV part of r42 (to 11-01 12:00 PKT), VAL ex attack, the attack window, per PKT day, and w/o the attack + w/o top 5."""
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/tune")
import tlib as T
P = [r for r in T.positions(["r42"])]
S = [s for s in T.skips(["r42"])]
print(f"r42 positions {len(P)} realized {sum(r['pnl'] for r in P):+.3f}")
LIVE = {"QUIET": "quiet", "create-slot": "create_slot", "age-1": "young_age", "10-sec (lone whale)": "lone_whale"}
LOG = {"bad creator (run only)": lambda r: r["gcr"], "safe sell timer": lambda r: r["st"], "ctx85": lambda r: r["ctx85"],
       "group risk": lambda r: r["grp"], "holder clock (approx)": lambda r: r["hc"], "landing guard": lambda r: r["guard"]}
def line(name, ty, vals, nall=None):
    s = T.summ(vals)
    return f"{name:24s} {ty} {nall if nall is not None else s['n']:5d} | win {s['win_n']:4d} {s['win']:+8.3f} | lose {s['lose_n']:4d} {s['lose']:+8.3f} | net {s['saved']:+7.3f}"
print("DASHBOARD reproduction (all r42)")
for nm, why in LIVE.items():
    ss = [s for s in S if s["why"] == why]
    print(line(nm, "LIVE", [s["paper"] for s in ss if s["paper"] is not None], len(ss)))
for nm, f in LOG.items():
    print(line(nm, "LOG ", [r["pnl"] for r in P if f(r)]))
U = [r["pnl"] for r in P if any(f(r) for f in LOG.values())]
print(line("LOG total unique", "LOG ", U))

# attack: template = fresh (<= 1 hold) holders at landing >= 35% (TAIL G3 feature) inside 11-02 08:00-08:40
att = [r for r in P if r["att"]]
tmpl = [r for r in att if r["fresh_sum"] >= 35]
print(f"\nattack window 11-02 08:00-08:40: {len(att)} trades {sum(r['pnl'] for r in att):+.3f}; template (fresh >= 35%) {len(tmpl)} {sum(r['pnl'] for r in tmpl):+.3f}"
      f" {T.pkt(min(r['t'] for r in tmpl)).strftime('%H:%M:%S')}..{T.pkt(max(r['t'] for r in tmpl)).strftime('%H:%M:%S')}")
for r in sorted(att, key=lambda r: r["t"]):
    print(f"  {T.pkt(r['t']).strftime('%H:%M:%S')} {r['kind']:5s} {r['mint'][:8]} {r['pnl']:+.4f} fresh {r['fresh_sum']:5.1f} ({r['fresh_n']}) whale {r['trig'].get('pct') or r['dump'].get('pct') or 0:4.1f}% age {r['trig'].get('age_slots') or r['dump'].get('age_slots')} sold {r['sold_in_hold']:.1f}"
          + " flags " + ",".join(n.split()[0] for n, f in LOG.items() if f(r)))
A0 = min(r["t"] for r in tmpl); A1 = max(r["t"] for r in tmpl)
def is_att(r): return r["run"] == "r42" and A0 - 60e9 <= r["t"] <= A1 + 60e9
# segments
SEG = {"r42-DEV": lambda r: r["per"] == "DEV", "VAL ex-att": lambda r: r["per"] == "VAL" and not is_att(r), "ATTACK": is_att}
for d in sorted({r["day"] for r in P} | {s["day"] for s in S}):
    SEG[f"day {d} ex-att"] = (lambda d: lambda r: r["day"] == d and not is_att(r))(d)
SEG["r42 ex-att"] = lambda r: not is_att(r)
out = {"dashboard": {}, "segments": {}, "attack": {"t0": T.pkt(A0).isoformat(), "t1": T.pkt(A1).isoformat(), "n_window": len(att),
       "sol_window": round(sum(r['pnl'] for r in att), 3), "n_template": len(tmpl), "sol_template": round(sum(r['pnl'] for r in tmpl), 3)}}
hours = {"r42-DEV": (T.SPLIT - min(r["t"] for r in P)) / 3.6e12}
print("\nPER SEGMENT (net saved = -sum; w/o5 = without the filter's 5 best saves)")
hdr = f"{'filter':24s}" + "".join(f" | {s:>22s}" for s in SEG)
print(hdr)
def cell(vals):
    s = T.summ(vals); return f"{s['n']:3d} {s['saved']:+6.3f} w/o5 {T.wo_top(vals):+6.3f}"
for nm, why in LIVE.items():
    row = f"{nm:24s}"; out["segments"][nm] = {}
    for sn, sf in SEG.items():
        v = [s["paper"] for s in S if s["why"] == why and sf(s) and s["paper"] is not None]
        row += f" | {cell(v):>22s}"; out["segments"][nm][sn] = dict(T.summ(v), wo5=T.wo_top(v), blocked_all=sum(1 for s in S if s['why'] == why and sf(s)))
    print(row)
for nm, f in LOG.items():
    row = f"{nm:24s}"; out["segments"][nm] = {}
    for sn, sf in SEG.items():
        v = [r["pnl"] for r in P if f(r) and sf(r)]
        row += f" | {cell(v):>22s}"; out["segments"][nm][sn] = dict(T.summ(v), wo5=T.wo_top(v))
    print(row)
row = f"{'base (all trades)':24s}"
for sn, sf in SEG.items():
    v = [r["pnl"] for r in P if sf(r)]; row += f" | {len(v):3d} {sum(v):+6.3f}           "
print(row)
json.dump(out, open("/home/moiz/sniper-data/filters3/tune/t1_reconcile.json", "w"), indent=1)
