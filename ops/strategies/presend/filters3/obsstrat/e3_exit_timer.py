#!/usr/bin/env python3
"""e3: exit timer grid on the hold tapes. Positions whose real exit was the 200 ms timer ("time-ms"): decide at our fill seen + X ms
instead (X < real: earlier; X > real: later, tape covers fill + 3 s), sell lands after this position's own measured delay L.
TP/SL exits unchanged. Per period and per run-day (PKT)."""
import sys, collections, datetime
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/obsstrat")
import tlib
HRS = {"DEV": 74.35, "VAL": 20.61}
XS = (0, 50, 100, 150, 250, 300, 400, 600)
res = collections.defaultdict(lambda: collections.defaultdict(float)); n = collections.Counter()
day = collections.defaultdict(lambda: collections.defaultdict(float))
rows = collections.defaultdict(lambda: collections.defaultdict(list))
for d in tlib.load():
    p = tlib.Pos(d)
    if not p.ok or p.why != "time-ms": continue
    per = d["per"]; n[per] += 1
    dk = datetime.datetime.utcfromtimestamp(d["t"] / 1e9 + 5 * 3600).strftime("%m-%d")
    for X in XS:
        T = p.tfill + X * 1e6
        if T + p.L > p.tape_end_t(): T = p.tape_end_t() - p.L
        cf, _ = p.proceeds_at(T)
        dd = (cf - p.act) * (1 - tlib.FEE_SELL) / 1e9
        res[per][X] += dd; day[dk][X] += dd; rows[per][X].append(dd)
print("timer exits:", dict(n), "| real decision = fill seen + ~200 ms; change vs real (SOL; /day; w/o its 5 best)")
for per in ("DEV", "VAL"):
    print(per, " ".join(f"{X}ms {res[per][X]:+.3f} ({res[per][X]/HRS[per]*24:+.2f}/d, w/o5 {sum(sorted(rows[per][X], reverse=True)[5:]):+.2f})" for X in XS))
print("by PKT day:")
for k in sorted(day): print("  ", k, " ".join(f"{X}:{day[k][X]:+.3f}" for X in XS))
