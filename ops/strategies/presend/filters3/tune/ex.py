#!/usr/bin/env python3
"""FILTER-TUNE extract: one run's pre-send records -> a compact pickle (read-only on the run file).
usage: ex.py rNN   -> /home/it/sniper-data/filters3/tune/ex_rNN.pkl
Keeps: every live position (arm / first fill / close / realized, record order), every live T2 skip (why, trigger, signals), the shadow
(presend_arm features, row c fill + exit), the live tape per mint (for the followed label), run_start config."""
import sys, json, pickle, collections
run = sys.argv[1]
src = f"/home/it/sniper-data/filters3/runs/{run}.presend.jsonl"
out = f"/home/it/sniper-data/filters3/tune/ex_{run}.pkl"
KEEP = ("presend_live_arm", "presend_live_fill", "presend_live_close", "presend_live_realized", "presend_live_skip", "presend_live_tape",
        "presend_arm", "presend_exit", "presend_fill", "presend_live_disarm", "presend_disarm", "run_start", "run_end")
arms, fills, closes, real, skips, tape = {}, {}, {}, [], [], collections.defaultdict(list)
sh_arm, sh_exit, sh_fill, sh_disarm, ldis = {}, {}, {}, {}, {}
rs = None; rearm_skips = collections.Counter(); seq = 0
for line in open(src, errors="replace"):
    if '"ev":"presend_' not in line and '"ev":"run_' not in line: continue
    if '"ev":"presend_attempt' in line or '"ev":"presend_wide' in line: continue
    d = json.loads(line); e = d.get("ev"); seq += 1
    if e not in KEEP: continue
    if e == "run_start":
        if rs is None: rs = d
        continue
    if e == "presend_live_tape":
        tape[d["mint"]].append((d["slot"], d.get("idx", 0), d["user"], bool(d["buy"]), d["sol"], d["t"], d.get("tok", 0)))
        continue
    mint = d.get("mint") or (d.get("trig") or {}).get("mint")
    k = (d.get("w"), mint)
    if e == "presend_live_arm":
        d["_seq"] = seq; arms[k] = d
    elif e == "presend_live_fill":
        if k not in fills: d["_seq"] = seq; fills[k] = d
    elif e == "presend_live_close": closes[k] = d
    elif e == "presend_live_realized": real.append((k, d["pnl"], d.get("kind", "t2"), seq))
    elif e == "presend_live_disarm": ldis[k] = {"why": d.get("why"), "quiet_stop": d.get("quiet_stop"), "filled": d.get("filled"), "t": d.get("t")}
    elif e == "presend_live_skip":
        if d.get("kind") == "rearm" or "trig" not in d:
            rearm_skips[d.get("why")] += 1; continue
        skips.append({"why": d.get("why"), "trig": d["trig"], "quiet": d.get("quiet"), "v2": d.get("v2"), "ann": d.get("ann"), "nb": d.get("nb"), "_seq": seq})
    elif e == "presend_arm":
        sh_arm[d["sig"]] = {k2: d.get(k2) for k2 in ("w", "mint", "pct", "age_slots", "sol", "vsol", "t", "slot", "wallet", "quiet", "v2")}
    elif e == "presend_exit" and d.get("row") == "c":
        sh_exit[d["w"]] = {"net_cheap": d.get("net_cheap", d.get("pnl", 0.0)), "pnl": d.get("pnl"), "why": d.get("why"), "hold_slots": d.get("hold_slots")}
    elif e == "presend_fill" and d.get("row", "c") == "c" and "entry" in d:
        if d.get("w") not in sh_fill:
            sh_fill[d["w"]] = {"sol_in": d["entry"].get("sol_in", 0) / 1e9, "drop_pct": d.get("drop_pct"), "sat": d.get("slots_after_trigger"),
                               "whale": d.get("seller_is_whale"), "n_ahead": d.get("n_ahead"), "slot": d.get("s_in")}
    elif e == "presend_disarm":
        sh_disarm[d["w"]] = {"why": d.get("why"), "qs": d.get("quiet_stop")}
pickle.dump({"run": run, "rs": rs, "arms": arms, "fills": fills, "closes": closes, "real": real, "skips": skips, "tape": dict(tape),
             "sh_arm": sh_arm, "sh_exit": sh_exit, "sh_fill": sh_fill, "sh_disarm": sh_disarm, "ldis": ldis, "rearm_skips": rearm_skips},
            open(out, "wb"), protocol=4)
print(run, "real", len(real), round(sum(p for _, p, _, _ in real) / 1e9, 4), "skips", len(skips), "sh_arm", len(sh_arm), "tape mints", len(tape))
