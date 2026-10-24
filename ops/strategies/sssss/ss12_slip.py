#!/usr/bin/env python3
# Slippage-limit / decision-moment probe (read-only): for each sssssDdM buy attempt (ok or failed), the price right before its
# tx vs the price after candidate decision moments in the same token: (a) the previous slot's last trade (slot start),
# (b) each same-slot trade before it. If its decision follows trade X and its limit is L, ok attempts have ratio_X <= L and
# failed ones > L: the fail rate vs ratio shows the limit. -> printed
import sys, json, zlib
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns")
import p4_eval as E
OUT = "/home/moiz/sniper-data/strategies/sssss"
run = sys.argv[1] if len(sys.argv) > 1 else "R2"
E.load([run]); d = E.DAYS[run]
att = json.load(open(f"{OUT}/att_{run}.json"))
rows = []
for a in att:
    q = a["q"]; t = int(d["tok"][q]); lo = q - int(d["F"][q, d["FI"]["ntr"]]) + 1
    pq = float(d["vsol"][q] / d["vtok"][q])
    # (a) slot start: last trade with slot < attempt slot
    j = q
    while j >= lo and d["s"][j] >= a["s"]: j -= 1
    r_start = pq / float(d["vsol"][j] / d["vtok"][j]) if j >= lo else None
    # (b) price before its tx vs the price 1, 2, 3 trades earlier (any wallet)
    r_k = []
    for back in (1, 2, 3, 5, 8):
        z = q - back
        r_k.append(pq / float(d["vsol"][z] / d["vtok"][z]) if z >= lo else None)
    # min price over the same slot before it (the cheapest moment it could have decided at)
    js = [x for x in range(j + 1, q + 1)] if j >= lo else []
    pmin = min([float(d["vsol"][x] / d["vtok"][x]) for x in js] + ([float(d["vsol"][j] / d["vtok"][j])] if j >= lo else [pq]))
    rows.append((a["ok"], r_start, r_k, pq / pmin, q - j))
ok = np.array([r[0] for r in rows])
def table(name, vals):
    v = np.array([x if x is not None else np.nan for x in vals])
    print(f"\n{name}: ok pctl {np.nanpercentile(v[ok == 1], [50, 90, 95, 99, 99.5, 100]).round(4).tolist()} | failed pctl {np.nanpercentile(v[ok == 0], [10, 25, 50, 75, 90]).round(4).tolist()}")
    for lo_, hi_ in ((0, 1.0), (1.0, 1.01), (1.01, 1.02), (1.02, 1.03), (1.03, 1.04), (1.04, 1.05), (1.05, 1.06), (1.06, 1.08), (1.08, 1.1), (1.1, 1.15), (1.15, 1.25), (1.25, 9)):
        m = (v >= lo_) & (v < hi_)
        if m.sum(): print(f"   ratio {lo_:.2f}-{hi_:.2f}: n {int(m.sum()):6d} fail rate {1 - ok[m].mean():.0%}")
table("price before its tx / price at slot start", [r[1] for r in rows])
table("price before its tx / price 1 trade earlier", [r[2][0] for r in rows])
table("price before its tx / price 3 trades earlier", [r[2][2] for r in rows])
table("price before its tx / min price this slot (incl. slot start)", [r[3] for r in rows])
print("\nsame-slot trades before its tx: ok", np.percentile([r[4] for r in rows if r[0]], [25, 50, 75, 90]).tolist(), "failed", np.percentile([r[4] for r in rows if not r[0]], [25, 50, 75, 90]).tolist())
