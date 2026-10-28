#!/usr/bin/env python3
"""migpaper validation: the windowed scorer (val models = m2/m3 train-only fits) on 10-28 vs migrate's replay rows
(feat.pkl / feat_p.pkl / sim_pre_2.0.pkl / sim_react_2.0.pkl). Joins on (mint, slot, idx); reports day totals, per-row
differences and the rows only one side has (with the reason). Usage: mp_validate.py [val/trades.jsonl]"""
import sys, os, json, pickle, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mplib import D, MIG, pkt, V
tr_f = sys.argv[1] if len(sys.argv) > 1 else f"{D}/val/trades.jsonl"
T = [json.loads(l) for l in open(tr_f)]
lo = min(t["window"] for t in T); hi = max(t["window"] for t in T) + 7200
print(f"scorer rows: {len(T)} entrable crossings in windows {pkt(lo).strftime('%m-%d %H:%M')}..{pkt(hi).strftime('%H:%M')} PKT, entered {sum(t['entered'] for t in T)}")
F = pickle.load(open(MIG + "/feat.pkl", "rb")); meta = F["meta"]; X = F["X"]; names = F["names"]
PP = pickle.load(open(MIG + "/feat_p.pkl", "rb"))
SIM = {m: pickle.load(open(MIG + f"/sim_{m}_2.0.pkl", "rb")) for m in ("pre", "react")}
EXI = {"stop": SIM["pre"]["EXITS"].index((2, 0.2, 120)), "pd": SIM["pre"]["EXITS"].index((2, "pd0.3", 120))}
RB = {m: {r["i"]: r for r in SIM[m]["R"]} for m in SIM}
rep = {}
for i, r in enumerate(meta):
    if r["V"] != V or r["ncross"] != 0 or not r["ent"]: continue
    rep[(r["mint"], r["slot"], r["k"])] = i
# replay rows by (mint, slot, idx): idx is not in meta -> join on (mint, slot) + k
rep_ms = collections.defaultdict(list)
for key, i in rep.items(): rep_ms[(key[0], key[1])].append(i)
def day_tot(rows_i, mode, ex):
    xi = EXI[ex]; return float(np.nansum([RB[mode][i]["res"][xi] for i in rows_i if i in RB[mode]]))
# ---- report side: 10-28 rows as the report counted them (day == 10-28, non-edge, p30 >= 0.8)
day = np.array([r["day"] for r in meta]); edge = np.array([r["edge"] for r in meta]); bt = np.array([r["bt"] for r in meta])
rep_day = [i for i in rep.values() if day[i] == "10-28" and not edge[i] and PP["p30"][i] >= 0.8]
rep_win = [i for i in rep.values() if lo <= bt[i] < hi and PP["p30"][i] >= 0.8]
rep_win_ne = [i for i in rep_win if not edge[i]]
print("\n== DAY TOTALS (SOL) ==")
print(f"report 10-28 (its definition: PKT day, non-edge rows, {len(rep_day)} entries): pre -20% {day_tot(rep_day, 'pre', 'stop'):+.3f} | pre pd {day_tot(rep_day, 'pre', 'pd'):+.3f} | react -20% {day_tot(rep_day, 'react', 'stop'):+.3f} | react pd {day_tot(rep_day, 'react', 'pd'):+.3f}")
print(f"replay restricted to the scored windows, incl. edge rows ({len(rep_win)}): pre -20% {day_tot(rep_win, 'pre', 'stop'):+.3f} | pre pd {day_tot(rep_win, 'pre', 'pd'):+.3f} | react -20% {day_tot(rep_win, 'react', 'stop'):+.3f} | react pd {day_tot(rep_win, 'react', 'pd'):+.3f}")
print(f"replay restricted to the scored windows, non-edge ({len(rep_win_ne)}): pre -20% {day_tot(rep_win_ne, 'pre', 'stop'):+.3f} | pre pd {day_tot(rep_win_ne, 'pre', 'pd'):+.3f} | react -20% {day_tot(rep_win_ne, 'react', 'stop'):+.3f} | react pd {day_tot(rep_win_ne, 'react', 'pd'):+.3f}")
E = [t for t in T if t["entered"]]
def s_tot(rows, mode, ex): return float(np.nansum([t[mode]["res"][0 if ex == "stop" else 1] for t in rows]))
print(f"scorer, same windows ({len(E)} entries): pre -20% {s_tot(E, 'pre', 'stop'):+.3f} | pre pd {s_tot(E, 'pre', 'pd'):+.3f} | react -20% {s_tot(E, 'react', 'stop'):+.3f} | react pd {s_tot(E, 'react', 'pd'):+.3f}")
# ---- row join
print("\n== ROW JOIN (entrable V=105 first crossings in the windows) ==")
only_s = []; both = []; dp30 = []
for t in T:
    cands = rep_ms.get((t["mint"], t["slot"]), [])
    if not cands: only_s.append(t); continue
    i = cands[0]; both.append((t, i)); dp30.append(t["p30"] - PP["p30"][i])
rep_in_win = [i for i in rep.values() if lo <= bt[i] < hi]
s_keys = {(t["mint"], t["slot"]) for t in T}
only_r = [i for i in rep_in_win if (meta[i]["mint"], meta[i]["slot"]) not in s_keys]
print(f"replay entrable rows in the windows: {len(rep_in_win)}; scorer: {len(T)}; joined {len(both)}; scorer-only {len(only_s)}; replay-only {len(only_r)}")
dp30 = np.array(dp30)
print(f"p30 (scorer val model vs feat_p.pkl) over joined rows: {np.isnan(dp30).sum()} replay rows unscored (edge, p=NaN); max |diff| {np.nanmax(np.abs(dp30)):.4f}, mean {np.nanmean(dp30):+.4f}, rows with |diff| > 0.01: {(np.abs(dp30) > 0.01).sum()}, selection flips (>=0.8 on one side only): {sum(1 for (t, i) in both if (t['p30'] >= 0.8) != (PP['p30'][i] >= 0.8))}")
# feature diffs on joined rows (which features differ?)
agei = names.index("age_s")
diffs = collections.Counter(); worst = {}
for t, i in both:
    pass
sel_both = [(t, i) for t, i in both if t["entered"] and PP["p30"][i] >= 0.8]
print(f"rows selected by both: {len(sel_both)}; selected by scorer only: {sum(1 for t, i in both if t['entered'] and PP['p30'][i] < 0.8)}; by replay only: {sum(1 for t, i in both if not t['entered'] and PP['p30'][i] >= 0.8)}")
for mode in ("pre", "react"):
    for ex, xi in (("stop", 0), ("pd", 1)):
        d = np.array([t[mode]["res"][xi] - RB[mode][i]["res"][EXI[ex]] for t, i in sel_both if i in RB[mode] and t[mode]["res"][xi] == t[mode]["res"][xi]])
        fl = np.array([t[mode]["fill"] - RB[mode][i]["fill"] for t, i in sel_both if i in RB[mode]])
        print(f"  {mode} {ex}: per-row P&L diff (scorer - replay) over {len(d)} rows: sum {d.sum():+.3f}, max |diff| {np.abs(d).max():.3f}, rows |diff|>0.01: {(np.abs(d) > 0.01).sum()}; fill diff sum {fl.sum():+.2f}")
print("\nlargest per-row P&L differences (pre -20%):")
dd = sorted([(abs(t["pre"]["res"][0] - RB["pre"][i]["res"][EXI["stop"]]), t, i) for t, i in sel_both if i in RB["pre"]], key=lambda z: -z[0])[:8]
for d_, t, i in dd:
    r = RB["pre"][i]
    print(f"  {t['pkt']} {t['mint'][:8]} scorer {t['pre']['res'][0]:+.3f} (fill {t['pre']['fill']:.1f}, tries {t['pre']['tries']:.0f}, unres {t['pre']['unresolved']}, kinds {t['pre']['kinds'][0]}) | replay {r['res'][EXI['stop']]:+.3f} (fill {r['fill']:.1f}, tries {r['tries']:.0f}, why {r['why']}) | p30 {t['p30']:.3f} vs {PP['p30'][i]:.3f} | grad {t['grad']} edge {edge[i]} tape_tail_s {t['tape_tail_s']}")
print("\nselection flips (joined rows where only one side has p30 >= 0.8):")
for t, i in both:
    if (t["p30"] >= 0.8) != (PP["p30"][i] >= 0.8):
        xs = X[i]; fd = ""
        if not np.isnan(PP["p30"][i]):
            import mplib
            fd = " | features differing: " + ", ".join(f"{names[j]} {t.get('_x', [None]*len(names))[j] if '_x' in t else '?'} vs {xs[j]:.3g}" for j in range(len(names)) if False)
        print(f"  {t['pkt']} {t['mint'][:8]} scorer p30 {t['p30']:.3f} replay {PP['p30'][i]:.3f} (edge {edge[i]}) age {t['age_s']} vs {xs[agei]:.0f} grad {t['grad']} scorer P&L pre-20% {t['pre']['res'][0] if t['entered'] else float('nan'):+.3f} replay P&L pre-20% {RB['pre'][i]['res'][EXI['stop']] if i in RB['pre'] else float('nan'):+.3f}")
print("\nreplay-only rows (in the windows, not produced by the scorer):")
for i in only_r[:15]:
    r = meta[i]; print(f"  {pkt(r['bt']).strftime('%m-%d %H:%M:%S')} {r['mint'][:8]} p30 {PP['p30'][i]:.3f} age {X[i, agei]:.0f}s edge {edge[i]} grad {r['grad']} has_mig {r['has_mig']} P&L pre-20% {RB['pre'][i]['res'][EXI['stop']] if i in RB['pre'] else float('nan'):+.3f}")
print("scorer-only rows:")
for t in only_s[:15]: print(f"  {t['pkt']} {t['mint'][:8]} p30 {t['p30']:.3f} age {t['age_s']} grad {t['grad']}")
