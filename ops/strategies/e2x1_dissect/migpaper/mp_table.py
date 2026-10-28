#!/usr/bin/env python3
"""migpaper: RUNNING.md (PKT) from out/results.jsonl + out/trades.jsonl. Usage: mp_table.py [results] [trades] [out.md] [--title S]"""
import sys, json, os, datetime as dt, collections
import numpy as np
D = "/home/moiz/sniper-data/e2x1_dissect/migpaper/out"
args = [x for x in sys.argv[1:] if not x.startswith("--")]
title = "migpaper RUNNING — paper forward test of the near-graduation rule (FROZEN.md)"
if "--title" in sys.argv: title = sys.argv[sys.argv.index("--title") + 1]
res_f = args[0] if len(args) > 0 else f"{D}/results.jsonl"
tr_f = args[1] if len(args) > 1 else f"{D}/trades.jsonl"
out_f = args[2] if len(args) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "RUNNING.md")
PKT = dt.timezone(dt.timedelta(hours=5))
now = dt.datetime.now(PKT).strftime("%m-%d %H:%M PKT")
R = [json.loads(l) for l in open(res_f)] if os.path.exists(res_f) else []
T = [json.loads(l) for l in open(tr_f)] if os.path.exists(tr_f) else []
E = [t for t in T if t.get("entered")]
EA = [t for t in T if t.get("entered_arm")]
ROWS = [("pre", 0, "pre-send 2 SOL, −20 % stop (HEADLINE)"), ("pre", 1, "pre-send 2 SOL, predictor-drop stop"),
        ("react", 0, "reactive 2 SOL, −20 % stop"), ("react", 1, "reactive 2 SOL, predictor-drop stop")]
DAYS = ["10-29", "10-30", "10-31"]
L = []; P = L.append
P(f"# {title}, updated {now}")
P("PAPER ONLY, local only. Expected SOL per entry over the 10 landing samples; costs 2.9 mSOL/trip + 0.005 mSOL per landed pre-send try + 0.3 mSOL per reactive revert (replay costs). `try0.3` = pre-send tries at 0.3 mSOL each; `rev0.005` = reactive reverts at 0.005 mSOL.")
P("")
P("**Row status (LOOKAHEAD_AUDIT.md, FROZEN.md 10-29 addendum): reactive row = clean; pre-send (crossing-gate) row has a known timing leak (LOOKAHEAD_AUDIT.md: its p30 gate uses the crossing trade, but the pre-sent tries go out before it); ARM-gate row = clean pre-send (same frozen p30 at the arm trade, vSOL ≥ 100).**")
P("")
if not R: P("(no windows scored yet)")
else:
    hrs = sum(r["end"] - r["start"] for r in R) / 3600; days_scored = hrs / 24
    P(f"Scored: {len(R)} windows = {hrs:.0f} h ({R[0]['start_pkt']} → {R[-1]['end_pkt']} PKT). Crossings of 105 in the windows: {sum(r['n_in_window'] for r in R)}, entrable {sum(r['n_entrable'] for r in R)}, p30 ≥ 0.8: {sum(r['n_selected'] for r in R)} entries, of which graduated {sum(r['n_grad'] for r in R)}.")
    P("")
    P("## Running totals (SOL)")
    P("| row | entries | fills | graduated | P&L graduated | P&L failed | total | SOL/day (running) | per entry | top-5 share | w/o top-5 | try0.3 / rev0.005 | unresolved | " + " | ".join(DAYS) + " | pass bar |")
    P("|---|---|---|---|---|---|---|---|---|---|---|---|---|" + "---|" * len(DAYS) + "---|")
    for mode, xi, lab in ROWS:
        rr = np.array([t[mode]["res"][xi] for t in E]) if E else np.zeros(0)
        g = np.array([t["grad"] for t in E], bool) if E else np.zeros(0, bool)
        fills = sum(t[mode]["fill"] for t in E); tot = float(np.nansum(rr))
        srt = np.sort(rr[~np.isnan(rr)])[::-1]; top5 = srt[:5].sum() if len(srt) else 0.0
        byday = {d: float(np.nansum([t[mode]["res"][xi] for t in E if t["day"] == d])) for d in DAYS}
        alt = float(np.nansum([t[mode]["res_try03"][xi] for t in E])) if mode == "pre" else float(np.nansum([t[mode]["res_rev005"][xi] for t in E]))
        unres = sum(1 for t in E if t[mode]["unresolved"])
        sd = tot / max(days_scored, 1e-9)
        done = [d for d in DAYS if any(r["start_pkt"].startswith(d) for r in R)]
        ok = sd >= 1.5 and all(byday[d] >= 0 for d in done)
        P(f"| {lab} | {len(E)} | {fills:.1f} | {int(g.sum())} | {float(np.nansum(rr[g])):+.3f} | {float(np.nansum(rr[~g])):+.3f} | **{tot:+.3f}** | **{sd:+.2f}** | {tot / max(fills, 1e-9):+.4f} | "
          f"{top5 / tot * 100 if tot > 0 else float('nan'):.0f}% | {tot - top5:+.3f} | {alt:+.3f} | {unres} | " + " | ".join(f"{byday[d]:+.2f}" for d in DAYS) + f" | {'PASS so far' if ok else 'fail so far'} |")
    rr = np.array([t["pre_arm"]["res"][0] for t in EA]) if EA else np.zeros(0)
    g = np.array([t["grad"] for t in EA], bool) if EA else np.zeros(0, bool)
    fills = sum(t["pre_arm"]["fill"] for t in EA); tot = float(np.nansum(rr))
    srt = np.sort(rr[~np.isnan(rr)])[::-1]; top5 = srt[:5].sum() if len(srt) else 0.0
    byday = {d: float(np.nansum([t["pre_arm"]["res"][0] for t in EA if t["day"] == d])) for d in DAYS}
    alt = float(np.nansum([t["pre_arm"]["res_try03"][0] for t in EA])); unres = sum(1 for t in EA if t["pre_arm"]["unresolved"])
    sd = tot / max(days_scored, 1e-9)
    P(f"| pre 2 SOL ARM-gate, −20 % stop (clean pre-send; not the pass-bar row) | {len(EA)} | {fills:.1f} | {int(g.sum())} | {float(np.nansum(rr[g])):+.3f} | {float(np.nansum(rr[~g])):+.3f} | **{tot:+.3f}** | **{sd:+.2f}** | {tot / max(fills, 1e-9):+.4f} | "
      f"{top5 / tot * 100 if tot > 0 else float('nan'):.0f}% | {tot - top5:+.3f} | {alt:+.3f} | {unres} | " + " | ".join(f"{byday[d]:+.2f}" for d in DAYS) + " | (info) |")
    P("")
    P("Pass bar (FROZEN.md): headline row ≥ +1.5 SOL/day over the 3 PKT days with each day ≥ 0 (+ replay check at the end). Days not yet scored show +0.00.")
    lk = [r for r in R if not r.get("lookahead_ok", True)]
    if lk: P(f"WARNING: {len(lk)} window(s) scored without a full look-ahead (tape ended early): " + ", ".join(r["start_pkt"] for r in lk))
    P("")
    P("## Per window (headline row = pre-send −20 % stop; react −20 % alongside)")
    P("| window (PKT) | cross | entrable | entries | grad | pre −20% | pre pd | react −20% | react pd | pre fills | pre tries | unres | ARM-gate entries | ARM-gate −20% | secs |")
    P("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in R:
        P(f"| {r['start_pkt']}–{r['end_pkt'][6:]} | {r['n_in_window']} | {r['n_entrable']} | {r['n_selected']} | {r['n_grad']} | {r['pre_stop']:+.3f} | {r['pre_pd']:+.3f} | {r['react_stop']:+.3f} | {r['react_pd']:+.3f} | {r['pre_fills']:.1f} | {r['pre_tries']:.0f} | {r['pre_unresolved']} | {r.get('n_selected_arm', '-')} | {(format(r['pre_arm_stop'], '+.3f') if 'pre_arm_stop' in r else '-')} | {r['secs']} |")
    P("")
    P("## Per day (PKT)")
    P("| day | entries | graduated | pre −20% | pre pd | react −20% | react pd | ARM-gate entries | ARM-gate −20% |")
    P("|---|---|---|---|---|---|---|---|---|")
    for d in sorted({t["day"] for t in E} | {t["day"] for t in EA}):
        e = [t for t in E if t["day"] == d]; ea = [t for t in EA if t["day"] == d]
        P(f"| {d} | {len(e)} | {sum(1 for t in e if t['grad'])} | " + " | ".join(f"{float(np.nansum([t[m]['res'][xi] for t in e])):+.3f}" for m, xi, _ in ROWS) + f" | {len(ea)} | {float(np.nansum([t['pre_arm']['res'][0] for t in ea])):+.3f} |")
    for mode, xi, lab in ROWS[:1] + ROWS[2:3]:
        P("")
        P(f"## 5 best / 5 worst entries — {lab}")
        P("| when (PKT) | token | p30 | vSOL | SOL left | age s | completed after | fill | fill vSOL | exit | SOL |")
        P("|---|---|---|---|---|---|---|---|---|---|---|")
        srt = sorted(E, key=lambda t: -(t[mode]["res"][xi] if t[mode]["res"][xi] == t[mode]["res"][xi] else -9))
        for t in srt[:5] + srt[-5:]:
            kinds = t[mode]["kinds"][xi]; kind = max(kinds, key=kinds.get) if kinds else "-"
            P(f"| {t['pkt']} | [{t['mint'][:8]}](https://gmgn.ai/sol/token/{t['mint']}) | {t['p30']:.2f} | {t['vsol']:.1f} | {t['sol_left']:.1f} | {t['age_s']} | "
              f"{(str(t['t_complete']) + ' s') if t['t_complete'] is not None else 'never'} | {t[mode]['fill']:.1f} | {t[mode]['fill_vs'] if t[mode]['fill_vs'] is not None else '-'} | {kind} | {t[mode]['res'][xi]:+.3f} |")
    P("")
    P("## Mechanics (all entries)")
    for mode in ("react", "pre"):
        w = collections.Counter()
        for t in E:
            for k, v in t[mode]["why"].items(): w[k] += v
        n = max(len(E), 1)
        P(f"- {mode}: fill {sum(t[mode]['fill'] for t in E) / n:.0%}, late (completed before landing) {w['late'] / n:.0%}, guard revert {w['guard'] / n:.0%}, pre-miss {w['pre_miss'] / n:.0%}, "
          f"pre-sent share of fills {np.mean([t[mode]['pre_share'] for t in E]) if E else 0:.0%}, we complete the curve {np.mean([t[mode]['we_complete'] for t in E]) if E else 0:.0%}, "
          f"mean fill vSOL {np.nanmean([t[mode]['fill_vs'] if t[mode]['fill_vs'] is not None else np.nan for t in E]) if E else float('nan'):.1f}, landing {np.nanmean([t[mode]['land_slots'] if t[mode]['land_slots'] is not None else np.nan for t in E]) if E else float('nan'):.2f} slots after the crossing, "
          f"sniped at open {np.mean([t[mode].get('sniped', False) for t in E if t['grad']]) if any(t['grad'] for t in E) else 0:.0%} of graduated, tries/entry {np.mean([t[mode]['tries'] for t in E]) if E else 0:.0f}")
    P("")
    P("Replay check (FROZEN.md pass bar, 2nd clause): deferred to the run end (needs ~1 GB temporary disk); not done yet.")
open(out_f, "w").write("\n".join(L) + "\n")
print("\n".join(L[:12]))
