#!/usr/bin/env python3
# Turn a speed probe (ops/final2/probe_speed.sh -> /root/run1/ps_*.jsonl) into the expected dip-backrun profit.
# Each landed probe's create->seen ms is read as our real reaction latency and priced on the independent check's curve
# (ops/overnight/verify_dip/VERIFY_DIP.md section 6: total SOL over 28.6 h of data, 0.5 SOL per trade, midpoints of its ranges).
# Probes that missed the create slot or never landed count as "slower than 75 ms". INFERRED estimate, per route.
# usage: python3 probe_to_pnl.py /root/run1/ps_*.jsonl
import sys, json, collections

CURVE = {  # real latency ms -> SOL per 28.6 h, at 0.0008 / 0.002 SOL per tx
    "0.0008": [(20, 16.3), (35, 10.45), (50, 2.2), (75, -6.5)],
    "0.002": [(20, 12.7), (35, 6.9), (50, -1.6), (75, -9.9)],
}
# 2026-10-23 afternoon version (ops/dip/PLAN.md "Real follower limits, full coverage"): direct pump sells only, spacing 5,
# 2-slot exit, best of unguarded / 2% guard per latency, six-block CV over ~33.5 h with real follower limits, replay "L" read as
# real L - 7 ms. SOL per 33.5 h at 0.0008 SOL per tx. Independent check of these afternoon claims pending.
# lenient (real follower limits + the checker's measured proxy errors, dip/real_latency.py) and strict (the checker's tolerance model)
CURVE_DIRECT = [(20, 22.0), (35, 17.4), (50, 12.0), (75, 8.0), (100, 2.0)]
CURVE_DIRECT_STRICT = [(20, 15.0), (35, 12.0), (50, 3.2), (75, 0.0), (100, -2.0)]
DIRECT_HOURS = 33.5

def interp(curve, x):
    if x <= curve[0][0]: return curve[0][1]
    if x >= curve[-1][0]: return curve[-1][1]
    for (x0, y0), (x1, y1) in zip(curve, curve[1:]):
        if x0 <= x <= x1: return y0 + (y1 - y0) * (x - x0) / (x1 - x0)

rows = [json.loads(l) for f in sys.argv[1:] for l in open(f) if l.strip()]
by = collections.defaultdict(list)
for r in rows: by[r.get("path", "?")].append(r)
print("route            probes  in create slot  median ms | base version SOL/day at 0.0008 / 0.002 SOL per tx | direct-only version SOL/day (strict … lenient)")
for p, v in sorted(by.items()):
    lat = []
    for r in v:
        ms = r.get("create_to_seen_ms")
        lat.append(ms if (ms is not None and r.get("seen_slot") == r.get("create_slot")) else 999.0)
    same = [x for x in lat if x < 999]
    med = sorted(same)[len(same) // 2] if same else None
    per_day = {k: sum(interp(c, x) for x in lat) / len(lat) * 24 / 28.6 for k, c in CURVE.items()}
    direct = sum(interp(CURVE_DIRECT, x) if x < 999 else 0.0 for x in lat) / len(lat) * 24 / DIRECT_HOURS
    strict = sum(interp(CURVE_DIRECT_STRICT, x) if x < 999 else 0.0 for x in lat) / len(lat) * 24 / DIRECT_HOURS
    print(f"{p:16s} {len(v):6d}  {len(same):14d}  {('%.1f' % med) if med is not None else '   -':>9} | {per_day['0.0008']:+6.1f} / {per_day['0.002']:+6.1f} | {strict:+6.1f} … {direct:+6.1f}")
print("\nGo if the best single route is ~+5 SOL/day or more at your real per-tx cost; otherwise the dip strategy is not worth building yet.")
