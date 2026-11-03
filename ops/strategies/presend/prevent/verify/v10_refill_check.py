#!/usr/bin/env python3
"""VERIFY step 10: read GUARDS' replay outputs (rp_*_sign0.15_open.json; data, not code) and split the guard's per-window change into
(a) removed fill, no refill, (b) refill (guard filled, different P&L), (c) new fill where base had none; mean over reps."""
import json, collections
D = "/home/moiz/sniper-data/prevent/guards"
tot = collections.Counter()
for run in ("f26", "f27", "f28", "r34", "r35", "r36", "r37"):
    d = json.load(open(f"{D}/rp_{run}_sign0.15_open.json")); reps = d["reps"]
    c = collections.Counter(); s = collections.Counter()
    for b_rows, g_rows in zip(d["base"], d["guard"]):
        for b, g in zip(b_rows, g_rows):
            assert b[0] == g[0] and b[1] == g[1]
            dv = g[4] - b[4]
            if b[3] and not g[3]: k = "removed_no_refill"
            elif b[3] and g[3] and abs(dv) > 1e-9: k = "refill_or_changed"
            elif not b[3] and g[3]: k = "new_fill"
            elif abs(dv) > 1e-9: k = "fees_only"
            else: continue
            c[k] += 1 / reps; s[k] += dv / reps
            if k == "refill_or_changed": s["refill_base_pnl"] += b[4] / reps; s["refill_new_pnl"] += g[4] / reps
    base = sum(sum(r[4] for r in rows) for rows in d["base"]) / reps
    print(f"{run}: base replay total {base:+.3f} | " + " | ".join(f"{k} n {c[k]:.1f} delta {s[k]:+.3f}" for k in ("removed_no_refill", "refill_or_changed", "new_fill", "fees_only"))
          + f" | refills: base pnl {s['refill_base_pnl']:+.3f} -> {s['refill_new_pnl']:+.3f}")
    for k in c: tot[k] += c[k]
    for k in s: tot["s_" + k] += s[k]
print("ALL:", {k: round(v, 3) for k, v in tot.items()})
