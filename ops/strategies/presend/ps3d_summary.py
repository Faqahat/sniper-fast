#!/usr/bin/env python3
# Step 1 summary: per pre-placer wallet, from the tapes (fills, the dump before each fill, token state, exit, P&L) and the raw
# streams (attempts, failed fees). P&L per wallet-token = sells x (1 - fee) - buys x (1 + fee) on the curve (tape), unsold rest = 0
# (flagged: share of tokens with > 5% left). Tx costs: failed-attempt fees from raw rows; tips / priority of fills not included.
import json, collections
import numpy as np
import ps_common as C
F = [json.loads(l) for l in open(f"{C.OUT}/ps3b_fills.jsonl")]
S = [json.loads(l) for l in open(f"{C.OUT}/ps3b_streams.jsonl")]
B = [json.loads(l) for l in open(f"{C.OUT}/ps3c_bursts.jsonl")]
HRS = {}
for day in ("R1", "R2", "R3", "R4"):
    a, b = C.WIN[day]; HRS[day] = (C.pk(b) - C.pk(a)) / 3600
q = lambda x, p: float(np.nanpercentile(np.array(x, float), p)) if len(x) else float("nan")
by = collections.defaultdict(list); bs = collections.defaultdict(list); bb = collections.defaultdict(list)
for r in F: by[r["w"]].append(r)
for r in S: bs[r["w"]].append(r)
for r in B: bb[r["w"]].append(r)
out = {}
print("PRE-PLACERS: fills from the tapes (MEASURED). dt = block-position proxy ms after the latest >= 2% sell (same slot).")
for w, R in sorted(by.items(), key=lambda x: -len(x[1])):
    days = collections.Counter(r["day"] for r in R)
    same = [r for r in R if r["same"]]; dd = [r for r in R if r.get("dump_move") is not None]
    tokp = collections.defaultdict(float); left = []
    for r in R:
        if r["tok_pnl"] != 0.0 or True: tokp[(r["day"], r["m"])] += r["tok_pnl"]
        left.append(r["tok_left_frac"])
    per_day = collections.defaultdict(float)
    for (day, m), v in tokp.items(): per_day[day] += v
    st = bs.get(w, []); fails = sum(x["n_buy_fail"] for x in st); ffee = sum(x["fail_fee"] for x in st) / 1e9
    nsell_att = sum(x["n_sell_att"] for x in st)
    att_mints = len({(x["day"], x["m"]) for x in st if x["n_buy_att"] > 0}); fill_mints = len({(x["day"], x["m"]) for x in st if x["n_buy_ok"] > 0})
    burst = bb.get(w, [])
    o = dict(fills=len(R), days=dict(days), fills_per_h={d: round(days[d] / HRS[d], 1) for d in days},
             same_slot=len(same) / len(R), dt_ms=[q([r["dump_dt_ms"] for r in same], p) for p in (25, 50, 75)],
             trades_between=q([r["trades_between"] for r in same], 50), first_after=np.mean([r["buys_between"] == 0 for r in same]) if same else None,
             dump_drop=[q([-r["dump_move"] for r in same], p) for p in (25, 50, 75)], dump_sol=q([r["dump_sol"] for r in same], 50),
             dumper_creator=np.mean([r["dumper_is_creator"] for r in same]) if same else None, dumper_insider=np.mean([r["dumper_wt"] == 2 for r in same]) if same else None,
             dumper_pct=q([r["dumper_pct_supply"] for r in same], 50), dumper_full_exit=np.mean([r["dumper_sold_frac"] >= 0.95 for r in same]) if same else None,
             dumper_held_slots=[q([r["dumper_last_buy_slots"] for r in same if r.get("dumper_last_buy_slots") is not None], p) for p in (25, 50, 75)],
             age_s=[q([r["age_s"] for r in R], p) for p in (25, 50, 75)], curve=q([r["curve"] for r in R], 50), size=q([r["sol"] for r in R], 50),
             ndumps_before=q([r["ndumps_before"] for r in R], 50), first_dump_age_slots=q([r.get("first_dump_slots") for r in R if r.get("first_dump_slots") is not None], 50),
             exit_slots=[q([r["exit_slots"] for r in R if "exit_slots" in r], p) for p in (25, 50, 75)], no_exit=np.mean(["exit_slots" not in r for r in R]),
             cre_pct=q([r["cre_pct"] for r in R], 50), big_pct=q([r["big_pct"] for r in R], 50),
             pnl_per_day={d: round(v, 3) for d, v in sorted(per_day.items())}, pnl_per_24h={d: round(per_day[d] / HRS[d] * 24, 2) for d in per_day},
             pnl_per_fill=sum(tokp.values()) / len(R), tok_left_gt5=np.mean([x > 0.05 for x in left]),
             fail_att=fails, fail_fee_sol=round(ffee, 3), fail_per_fill=fails / max(len(R), 1), sell_att=nsell_att,
             mints_attempted=att_mints, mints_filled=fill_mints,
             burst_start_age_s=[q([r["age_burst_s"] for r in burst if r.get("age_burst_s") is not None], p) for p in (25, 50, 75)],
             burst_slots=[q([r["burst_slots"] for r in burst], p) for p in (25, 50, 75)],
             burst_attempts=q([r["burst_n"] for r in burst], 50))
    out[w] = o
    print(f"\n### {w}  fills {o['fills']} {o['days']}  ({o['fills_per_h']} per h)")
    print(f"   same-slot after a >=2% dump {100 * o['same_slot']:.0f}%; dt p25/50/75 {o['dt_ms'][0]:.1f}/{o['dt_ms'][1]:.1f}/{o['dt_ms'][2]:.1f} ms; trades between {o['trades_between']:.0f}; first buyer after dump {100 * (o['first_after'] or 0):.0f}%")
    print(f"   dump drop p25/50/75 {o['dump_drop'][0]:.1f}/{o['dump_drop'][1]:.1f}/{o['dump_drop'][2]:.1f}%, sell {o['dump_sol']:.2f} SOL; dumper = creator {100 * (o['dumper_creator'] or 0):.0f}%, insider {100 * (o['dumper_insider'] or 0):.0f}%, "
          f"held {o['dumper_pct']:.1f}% of supply, full exit {100 * (o['dumper_full_exit'] or 0):.0f}%, held for {o['dumper_held_slots'][1]:.0f} slots (p25 {o['dumper_held_slots'][0]:.0f}, p75 {o['dumper_held_slots'][2]:.0f})")
    print(f"   token age at fill p25/50/75 {o['age_s'][0]:.0f}/{o['age_s'][1]:.0f}/{o['age_s'][2]:.0f} s; curve {o['curve']:.0f} SOL; size {o['size']:.2f} SOL; >=2% dumps before {o['ndumps_before']:.0f}; creator holds {o['cre_pct']:.1f}%, biggest holder {o['big_pct']:.1f}%")
    print(f"   exit after p25/50/75 {o['exit_slots'][0]:.0f}/{o['exit_slots'][1]:.0f}/{o['exit_slots'][2]:.0f} slots (no sell seen {100 * o['no_exit']:.0f}%); P&L on curve {o['pnl_per_fill']:+.4f}/fill, per day {o['pnl_per_day']}, per 24h {o['pnl_per_24h']}; tokens with >5% unsold {100 * o['tok_left_gt5']:.0f}%")
    print(f"   attempts: failed buys {o['fail_att']} ({o['fail_per_fill']:.0f}/fill, fees {o['fail_fee_sol']:.2f} SOL), sell attempts {o['sell_att']}; mints attempted {o['mints_attempted']}, filled {o['mints_filled']}; "
          f"burst start age p25/50/75 {o['burst_start_age_s'][0]:.0f}/{o['burst_start_age_s'][1]:.0f}/{o['burst_start_age_s'][2]:.0f} s, burst slots {o['burst_slots'][1]:.0f}, burst attempts {o['burst_attempts']:.0f}")
json.dump(out, open(f"{C.OUT}/ps3d_summary.json", "w"), indent=1, default=float)
