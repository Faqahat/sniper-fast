#!/usr/bin/env python3
"""FILTERS-3 AUDIT step 5: the tables (markdown) and audit.json from core.pkl (audit.py) and quiet.pkl / quiet.json (quiet.py).
usage: report.py  -> /home/it/sniper-data/filters3/audit/{tables.md, audit.json} (+ a copy of audit.json next to REPORT.md)"""
import pickle, json, collections, time, shutil
A = "/home/it/sniper-data/filters3/audit"; D = "/home/it/sniper/ops/strategies/presend/filters3/audit"
C = pickle.load(open(f"{A}/core.pkl", "rb")); TAB, ITEMS, CAL, POS = C["TAB"], C["ITEMS"], C["CAL"], C["POS"]
Q = json.load(open(f"{A}/quiet.json"))
RUNS = [f"r{i}" for i in range(37, 47)]
CUT = int(time.mktime(time.strptime("2026-11-01 07:00:00", "%Y-%m-%d %H:%M:%S")) - time.timezone) * 10**9
def pkt(t): return time.strftime("%m-%d %H:%M", time.gmtime(t / 1e9 + 5 * 3600)) if t else "?"

def summ(vals):
    v = [x for x in vals if x is not None]
    w = [x for x in v if x > 0]; l = [x for x in v if x <= 0]
    net = sum(v); saved = -net; s = sorted(v)
    rest = s[5:] if saved >= 0 else (s[:-5] if len(s) > 5 else [])
    return dict(n=len(v), wn=len(w), ws=sum(w), ln=len(l), ls=sum(l), net=net, saved=saved, saved_wo5=-sum(rest))

# hours per period (r42 split at the cut by its own span)
H = {"DEV": 0.0, "VAL": 0.0, "HOLD": 0.0}
for run in RUNS:
    h = TAB[run]["hours"]
    if run == "r42":
        f, l = TAB[run]["first"], TAB[run]["last"]; fr = (CUT - f) / (l - f)
        H["DEV"] += h * fr; H["VAL"] += h * (1 - fr)
    elif run >= "r43": H["HOLD"] += h
    else: H["DEV"] += h
H["ALL"] = sum(H.values())

NAMES = collections.OrderedDict([
    ("skip:quiet", ("LIVE", "QUIET skip (T2)")), ("skip:create_slot", ("LIVE", "create-slot skip")), ("skip:young_age", ("LIVE", "age-1 skip (min age 2)")),
    ("skip:lone_whale", ("LIVE", "lone whale (10-sec) skip")), ("stop:quiet_t2", ("LIVE", "QUIET stop T2 5:2 (live windows)")),
    ("stop:quiet_t2_shadow_all", ("INFO", "QUIET stop T2 5:2 (shadow, every trigger)")), ("live:deep_limit_refused", ("LIVE", "deeper limit 0.85: refused windows (r40)")),
    ("live:deep_limit_deep_fills", ("LIVE", "deeper limit: fills that came deep (r40, real)")),
    ("log:safe_sell_timer", ("LOG", "safe sell timer")), ("log:holder_clock", ("LOG", "holder clock (approx)")), ("log:group_risk", ("LOG", "group risk")),
    ("log:landing_guard", ("LOG", "landing guard")), ("log:ctx85", ("LOG", "ctx85 (deeper-limit log)")), ("log:bad_creator", ("LOG", "bad creator (chained ledger)")),
    ("log:quiet_v2", ("LOG", "QUIET v2 (log)")), ("log:quiet_warmup_would_skip", ("LOG", "QUIET would-skip in warm-up")),
    ("log:nb50_le2_t2", ("LOG", "nb50 <= 2 (T2, descriptive)")), ("log:nb50_le1_rearm", ("LOG", "nb50 <= 1 (re-arm, descriptive)")),
    ("log:UNION_core6", ("LOG", "UNION of 6 log rules")), ("log:wide_shadow_3to6", ("ADD", "wide shadow 3-6% (trades ADDED)")),
])
MECH = ["skip:blocked_armed", "skip:blocked_position", "skip:blocked_ata_open", "skip:no_launch_accounts", "skip:legacy_create", "skip:stopped"]

def gain_wo5(vals):
    v = sorted(x for x in vals if x is not None); return sum(v[:-5]) if len(v) > 5 else 0.0
def fmt_row(label, ty, trig, e, pp=None, vals=None):
    if e is None: return f"| {label} | {ty} | {trig if trig is not None else ''} | - | - | - | - | - | - |"
    if ty == "ADD":
        return f"| {label} | {ty} | {trig if trig is not None else ''} | {e['n']} | {e['wn']} / {e['ws']:+.3f} | {e['ln']} / {e['ls']:+.3f} | gain {e['net']:+.3f} | gain w/o top5 {gain_wo5(vals or []):+.3f} | {(pp['net'] if pp else 0):+.3f} |"
    return f"| {label} | {ty} | {trig if trig is not None else ''} | {e['n']} | {e['wn']} / {e['ws']:+.3f} | {e['ln']} / {e['ls']:+.3f} | **{e['saved']:+.3f}** | {e['saved_wo5']:+.3f} | {(-pp['net'] if pp else 0):+.3f} |"
HDR = "| filter | type | touched | n with money | won n / SOL | lost n / SOL | saved (block value) | saved w/o top 5 | raw paper saved |\n|---|---|---:|---:|---:|---:|---:|---:|---:|"

out = []; J = {"runs": {}, "totals": {}, "calibration": CAL, "hours": H}
for run in RUNS:
    T = TAB[run]; R = T["rows"]
    out.append(f"\n### {run}  ({pkt(T['first'])} -> {pkt(T['last'])} PKT, {T['hours']:.1f} h, {T['n']} trades, real {T['pnl']:+.3f} SOL, win {T['win']}/{T['n']}; T2 {T['t2']['n']} {T['t2']['net']:+.3f}, re-arm {T['rearm']['n']} {T['rearm']['net']:+.3f}; calibration {CAL[run]['gap']*1000:+.1f} mSOL/window on {CAL[run]['pairs']} pairs)\n")
    out.append(HDR)
    J["runs"][run] = {"hours": T["hours"], "trades": T["n"], "real": T["pnl"], "win": T["win"], "t2": T["t2"], "rearm": T["rearm"], "calibration": CAL[run], "filters": {}, "overlap": T["overlap"]}
    for k, (ty, label) in NAMES.items():
        if k not in R: continue
        r = R[k]
        if k.startswith("log:") and r["est"]["n"] == 0 and r.get("trig") == 0: continue
        out.append(fmt_row(label, ty, r["trig"], r["est"], r.get("paper"), [x[1] for x in ITEMS.get((run, k), [])]))
        J["runs"][run]["filters"][k] = {"type": ty, "touched": r["trig"], "money": r["est"], "paper": r.get("paper")}
    rq = R.get("stop:quiet_rearm")
    if rq: out.append(f"| QUIET stop re-arm 6:2 | LIVE | {rq['trig']} | see QUIET section (raw proxy) | | | | | |"); J["runs"][run]["filters"]["stop:quiet_rearm"] = {"type": "LIVE", "touched": rq["trig"]}
    rs = [(k, v) for k, v in R.items() if k.startswith("rearm_skip:") and v["type"] == "LIVE"]
    for k, v in rs:
        out.append(f"| {k.replace('rearm_skip:', 're-arm skip ')} | LIVE | {v['trig']} | no shadow: not measurable | | | | | |"); J["runs"][run]["filters"][k] = {"type": "LIVE", "touched": v["trig"]}
    mech = [(k, R[k]) for k in MECH if k in R]
    if mech:
        out.append(f"\nMechanical skips (not filters): " + ", ".join(f"{k[5:]} {v['trig']} (est {v['est']['net']:+.3f})" for k, v in mech))
    ov = {k: v for k, v in T["overlap"].items()}
    if ov: out.append("\nOverlap (same trade flagged by both): " + ", ".join(f"{k.replace('log:', '')} {v}" for k, v in sorted(ov.items(), key=lambda kv: -kv[1])[:10]))
    sq = R.get("skip:quiet")
    if sq: out.append(f"\nLive-skip overlap: of {sq['trig']} QUIET skips, {sq.get('ov_lone', 0)} also lone-whale (nb<=1), {sq.get('ov_v2', 0)} also QUIET-v2 skip. " +
                      ", ".join(f"{k[5:]}: {R[k].get('ov_quiet_all4', 0)} of {R[k]['trig']} had QUIET all-4 true" for k in ("skip:create_slot", "skip:young_age", "skip:lone_whale") if k in R))

# totals by period
out.append("\n## TOTAL, all runs, by period (DEV = r37-r41 + r42 to 11-01 12:00 PKT; VAL = r42 after; HOLD = r43-r46)\n")
out.append(f"Hours: DEV {H['DEV']:.1f}, VAL {H['VAL']:.1f}, HOLD {H['HOLD']:.1f}, ALL {H['ALL']:.1f}. 'ALL saved/day' = ALL saved x 24 / the hours of the runs where the rule ran (ADD rows: gain/day).\n")
out.append("| filter | type | DEV saved (n) | DEV w/o5 | VAL saved (n) | VAL w/o5 | HOLD saved (n) | HOLD w/o5 | ALL saved (n) | ALL w/o5 | ALL saved/day | ALL won n/SOL | ALL lost n/SOL |\n|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
for k, (ty, label) in list(NAMES.items()) + [(m, ("MECH", m[5:])) for m in MECH]:
    J["totals"][k] = {}
    cells = []
    for per in ("DEV", "VAL", "HOLD", "ALL"):
        v = [x[1] for run in RUNS for x in ITEMS.get((run, k), []) if per == "ALL" or x[0] == per]
        trig = sum(1 for run in RUNS for x in ITEMS.get((run, k), []) if per == "ALL" or x[0] == per)
        s = summ(v); J["totals"][k][per] = dict(s, touched=trig, per_day=s["saved"] * 24 / H[per] if H[per] else 0)
        if ty == "ADD": cells.append(f"gain {s['net']:+.3f} ({s['n']}) | {gain_wo5(v):+.3f}")
        else: cells.append(f"{s['saved']:+.3f} ({s['n']}) | {s['saved_wo5']:+.3f}")
    a = J["totals"][k]["ALL"]
    if a["n"] == 0 and a["touched"] == 0: continue
    hrs = sum(TAB[run]["hours"] for run in RUNS if (TAB[run]["rows"].get(k) or {}).get("trig"))     # hours of the runs where the rule ran
    a["hours_active"] = hrs; a["per_day"] = a["saved"] * 24 / hrs if hrs else 0
    pd = a["per_day"] if ty != "ADD" else -a["per_day"]
    out.append(f"| {label} | {ty} | " + " | ".join(cells) + f" | {pd:+.2f} | {a['wn']} / {a['ws']:+.3f} | {a['ln']} / {a['ls']:+.3f} |")
# raw-paper totals for the live skips (no calibration)
out.append("\nRaw paper (no calibration) for the live skips, ALL: " + ", ".join(
    f"{NAMES[k][1]} {-sum(x[3] for run in RUNS for x in ITEMS.get((run, k), []) if x[3] is not None):+.3f}" for k in ("skip:quiet", "skip:create_slot", "skip:young_age", "skip:lone_whale", "stop:quiet_t2")))
# pooled calibration sensitivity
pp = sum(CAL[r]["paper"] for r in RUNS); pl = sum(CAL[r]["live"] for r in RUNS); pn = sum(CAL[r]["pairs"] for r in RUNS); g = (pl - pp) / pn
out.append(f"\nPooled calibration instead of per-run: {g*1000:+.2f} mSOL/window ({pn} pairs, paper {pp:+.3f} vs live {pl:+.3f}). With it, ALL saved: " + ", ".join(
    f"{NAMES[k][1]} {-sum(x[3] + g for run in RUNS for x in ITEMS.get((run, k), []) if x[3] is not None):+.3f}" for k in ("skip:quiet", "skip:create_slot", "skip:young_age", "skip:lone_whale", "stop:quiet_t2")))
J["pooled_gap_msol"] = g * 1000
J["quiet"] = Q
open(f"{A}/tables.md", "w").write("\n".join(out) + "\n")
json.dump(J, open(f"{A}/audit.json", "w"), indent=1, default=str)
shutil.copy(f"{A}/audit.json", f"{D}/audit.json")
print("\n".join(out[-40:]))
