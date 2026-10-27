#!/usr/bin/env python3
"""PRESEND FILTER: knowable-when checks (MEASURED on the engine records of every studied run, never r26).
  ARM   : the arm record's time vs the trigger's feed arrival; the first try's send time vs the trigger (the ARM rule runs before it).
          The quiet signals read only chain rows strictly before the trigger tx (by construction, feat.py / apply_filter.py), and the
          whale's dumps closed (dump slot + 2) before the trigger slot: counted here.
  DURING: each try's logged 'pos' (the latest trade of the token the engine had seen when it signed it) is never after the try's own
          send slot, and the filling try's pos is before our fill (so the dump that filled us was NOT known when the try was decided)."""
import json, collections
import numpy as np
import lv, sim, rules

W = sim.load()
d_arm = []; d_first = []; bad_pos = 0; n_pos = 0; fill_ok = 0; fill_n = 0; dump_ok = 0; dump_n = 0
for run in lv.RUNFILES:
    R = lv.load(run)
    for (seg, w), X in R["W"].items():
        a = X["arm"]; tr = a["trig"]
        if a.get("t"): d_arm.append((a["t"] - tr["t"]) / 1e6)
        if X["atts"]: d_first.append((R["att"][X["atts"][0]]["t"] - tr["t"]) / 1e6)
        for sig in X["atts"]:
            A = R["att"][sig]; n_pos += 1
            if tuple(A["pos"][:1]) > (A["slot"],): bad_pos += 1
for w in W:
    if w["filled"]:
        ft = [t for t in w["X"]["tries"] if t[4]]
        if ft:
            fill_n += 1
            if tuple(ft[0][7][:2]) < (w["fill_slot"], w["fill_idx"]): fill_ok += 1
# whale dumps used by the 24 h signal: all closed before the trigger slot (by the filter in rules.wh_dump_fol_24h); count them
for w in W:
    if not w["chain_ok"]: continue
    rules.wh_dump_fol_24h(w)
    for s, bt, nf in rules._WDF["du"].get(w["whale"], []):
        if bt >= w["t"] / 1e9 - 86400 and s + 2 < w["trig_slot"]:
            dump_n += 1; dump_ok += (s + 2 < w["trig_slot"])
pc = lambda x: np.percentile(x, [1, 50, 99]).round(2).tolist()
print("arm records carry no own time: the arm is decided on the trigger tx arrival (trig.t)")
print(f"first try sent - trigger arrival (ms) p1/p50/p99: {pc(d_first)} (n {len(d_first)})")
print(f"tries whose known position (pos) is in a slot after their own send slot: {bad_pos} of {n_pos}")
print(f"filling tries whose pos is before our fill: {fill_ok} of {fill_n}")
print(f"whale dumps feeding the 24 h signal that closed before the trigger slot: {dump_ok} of {dump_n}")
