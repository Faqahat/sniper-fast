#!/usr/bin/env python3
"""TAIL t3: one-feature scan (DEV vs VAL): per bin n, sum P&L, mean mSOL, big-loss SOL. Research only (picks thresholds on DEV)."""
import json, sys, collections
T = "/home/moiz/sniper-data/filters3/tail"
rows = json.load(open(f"{T}/dissect_rows.json"))
def scan(name, fn, edges, only=None):
    print(f"\n-- {name}" + (f" [{only}]" if only else ""))
    for st in ("DEV", "VAL"):
        R = [r for r in rows if r["set"] == st and r["F"].get("has_ann") and (only is None or r["kind"] == only)]
        b = collections.defaultdict(list)
        for r in R:
            v = fn(r["F"])
            if v is None: b["na"].append(r["pnl"]); continue
            lab = next((f"<{e}" for e in edges if v < e), f">={edges[-1]}")
            b[lab].append(r["pnl"])
        order = [f"<{e}" for e in edges] + [f">={edges[-1]}", "na"]
        print(f"  {st}: " + " | ".join(f"{k}: {len(b[k])} {sum(b[k]):+.2f} ({1000*sum(b[k])/len(b[k]):+.0f}) L{sum(x for x in b[k] if x<-0.04):+.2f}" for k in order if b[k]))
F = lambda k: (lambda f: f.get(k))
for only in ([] if "--only" in sys.argv else [None]):
    scan("ob6 (max other holder at signing, exact)", F("ob6"), [3, 6, 9, 12, 15], only)
    scan("max_oth", F("max_oth"), [3, 6, 9, 12, 15], only)
    scan("bundle (same-age fresh sum)", F("bundle"), [5, 10, 20, 30, 40], only)
    scan("sum_fresh", F("sum_fresh"), [5, 10, 20, 30, 40], only)
    scan("samage (same-age any)", F("samage"), [5, 10, 20, 30, 40], only)
    scan("sum_oth", F("sum_oth"), [5, 10, 20, 30, 40], only)
    scan("n_oth6", F("n_oth6"), [1, 2, 3], only)
    scan("whale_fresh", lambda f: int(f.get("whale_fresh")), [1], only)
    scan("max_oth_n (holds of biggest other)", F("max_oth_n"), [1, 2, 5, 10, 16], only)
    scan("resid (curve sold - listed)", F("resid"), [10, 20, 30, 40], only)
    scan("sold_pct", F("sold_pct"), [30, 40, 50, 60, 70], only)
    scan("vsol", F("vsol"), [40, 50, 60, 80, 100], only)
    scan("age", F("age"), [5, 10, 20, 50, 150, 1000], only)
    scan("w_pct", F("w_pct"), [7, 8, 10, 15], only)
    scan("risky_sum (approx signing)", F("risky_sum"), [0.01, 3, 6, 10], only)
    scan("sign_after_trig", F("sign_after_trig"), [2, 4, 6, 8], only)
    scan("nb50", F("nb50"), [3, 6, 10, 15, 25], only)
    scan("cr_pct", F("cr_pct"), [0.01, 3, 6], only)
if "--only" in sys.argv:
    for k in ("t2", "rearm"):
        scan("whale_sign", F("whale_sign"), [0.5, 3, 6, 9, 12], k)
        scan("whale_rem", F("whale_rem"), [0.1, 0.5, 0.9, 1.01], k)
