#!/usr/bin/env python3
"""FILTERS-3 AUDIT step 1: one run's presend records -> a compact pickle (read-only on the input).
usage: extract.py RUN_TAG IN.jsonl OUT.pkl
Keeps: segments (run_start/run_end), live arms/skips/disarms/fills/exits/closes/realized/tape, ok attempt landings, stops,
the main shadow (presend_arm/_fill/_exit/_disarm/_skip, row c) and the wide shadow (row c)."""
import sys, json, pickle, collections
tag, src, dst = sys.argv[1:4]
seg = 0
S = dict(starts=[], ends=[], larm={}, ldis={}, lfill={}, lexit={}, lclose={}, lreal=[], tape=collections.defaultdict(list), att_ok={},
         skips=[], rskips=[], stops=[], fee_pause=[], sh_arm={}, sh_fill={}, sh_exit={}, sh_dis={}, sh_skip=[], wa={}, wf={}, wx={}, defers=0)
KEEP_ARM = ("kind", "w", "mint", "spend", "drop", "en_slot", "quiet", "quiet_skip", "v2", "ann", "nb", "dump", "holders", "arm_slot", "check_slot", "deferred_ms", "gap")
for line in open(src, errors="replace"):
    if '"ev":"presend_' not in line and '"ev":"run_' not in line: continue
    if seg == 0 and '"ev":"presend_live_quiet_state"' not in line and '"ev":"run_' not in line: seg = 1   # no marker (should not happen)
    # cheap prefilter: drop the per-attempt sends; keep ok landings only
    if '"ev":"presend_attempt"' in line: continue
    if '"ev":"presend_attempt_land"' in line and '"res":"ok"' not in line: continue
    if '"ev":"presend_live_ata' in line or '"ev":"presend_live_end_check"' in line or '"ev":"presend_live_parity"' in line: continue
    d = json.loads(line); e = d["ev"]
    # run_start / run_end lines sit at the END of these files: a process's first record (presend_live_quiet_state) marks a segment
    if e == "presend_live_quiet_state": seg += 1; S.setdefault("qstate", []).append(d); continue
    if e == "run_start":
        S["starts"].append(dict(t=d["t"], presend_live=d.get("presend_live", {}), limits=d.get("limits"), presend=d.get("presend"))); continue
    if e == "run_end": S["ends"].append(dict(t=d.get("t"))); continue
    if e == "presend_live_arm":
        k = (seg, d["w"]); a = {x: d.get(x) for x in KEEP_ARM if x in d}; a["kind"] = d.get("kind", "t2")
        if "trig" in d: a["trig"] = d["trig"]
        if "mint" not in a: a["mint"] = (d.get("trig") or {}).get("mint")
        S["larm"][k] = a
    elif e == "presend_live_disarm": S["ldis"][(seg, d["w"])] = d
    elif e == "presend_live_fill":
        k = (seg, d["w"], d["mint"])
        if k not in S["lfill"]: S["lfill"][k] = d
        else: S["lfill"][k].setdefault("extra_fills", []).append({x: d.get(x) for x in ("slot", "idx", "t", "sol_in", "sig")})
    elif e == "presend_live_exit": S["lexit"].setdefault((seg, d["w"], d["mint"]), d)
    elif e == "presend_live_close": S["lclose"][(seg, d["w"], d["mint"], d.get("pid"))] = {x: d.get(x) for x in ("exit_slot", "exit_why", "held_s", "sell_lands", "land", "buys", "kind", "result", "rounds", "spend", "curve_pnl", "via", "client", "path")}
    elif e == "presend_live_realized": d["seg"] = seg; d.pop("buys", None); S["lreal"].append(d)
    elif e == "presend_live_tape": S["tape"][d["mint"]].append((d["slot"], d["idx"], d["user"], d["buy"], d["sol"], d["t"], d.get("vsol"), d.get("vtok")))
    elif e == "presend_attempt_land": S["att_ok"][d["sig"]] = {x: d.get(x) for x in ("w", "mint", "slot", "idx", "after", "between", "n_between", "instant_before_us", "instant_after_us", "d", "x", "ms_after_d_rx", "kind")}
    elif e == "presend_live_skip":
        d["seg"] = seg
        if d.get("kind") == "rearm": S["rskips"].append({x: d.get(x) for x in ("seg", "why", "mint", "dump", "check_slot", "en_slot", "holders")})
        else: S["skips"].append(d)
    elif e == "presend_live_stop": d["seg"] = seg; S["stops"].append(d)
    elif e in ("presend_live_fee_pause", "presend_live_fee_resume"): S["fee_pause"].append(d)
    elif e == "presend_live_rearm_defer": S["defers"] += 1
    elif e == "presend_arm": S["sh_arm"][(seg, d["w"])] = {x: d.get(x) for x in ("sig", "mint", "wallet", "pct", "age_slots", "slot", "t", "quiet", "v2", "sol")}
    elif e == "presend_fill" and d.get("row") == "c": S["sh_fill"][(seg, d["w"])] = dict(s_in=d.get("s_in"), sol_in=(d.get("entry") or {}).get("sol_in"), sat=d.get("slots_after_trigger"), drop=d.get("drop_pct"), t=(d.get("m") or {}).get("t"), n_ahead=d.get("n_ahead"))
    elif e == "presend_exit" and d.get("row") == "c": S["sh_exit"][(seg, d["w"])] = dict(net=d.get("net_cheap", d.get("pnl", 0.0)), pnl=d.get("pnl"), exit_slot=d.get("exit_slot"), why=d.get("why"))
    elif e == "presend_disarm": S["sh_dis"][(seg, d["w"])] = dict(why=d.get("why"), qs=d.get("quiet_stop"), cfill=((d.get("rows") or {}).get("c") or {}).get("filled"))
    elif e == "presend_skip": S["sh_skip"].append({x: d.get(x) for x in ("why", "mint", "sig", "slot", "t", "pct")})
    elif e == "presend_wide_arm": S["wa"][(seg, d["w"])] = {x: d.get(x) for x in ("sig", "mint", "wallet", "pct", "age_slots", "slot", "t")}
    elif e == "presend_wide_fill" and d.get("row") == "c": S["wf"][(seg, d["w"])] = (d.get("entry") or {}).get("sol_in")
    elif e == "presend_wide_exit" and d.get("row") == "c": S["wx"][(seg, d["w"])] = d.get("net_cheap", d.get("pnl", 0.0))
S["tape"] = dict(S["tape"])
pickle.dump(S, open(dst, "wb"))
print(tag, {k: (len(v) if hasattr(v, "__len__") else v) for k, v in S.items()})
