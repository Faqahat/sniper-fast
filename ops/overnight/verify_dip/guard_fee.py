#!/usr/bin/env python3
"""verify_dip / guard_fee: the claim's L35 picks by entry price vs the post-sell price (trades ahead of us), the effect of a
min-tokens-out guard (1/2/5%), and the fee tiers seen on the sells (fee_bps + creator_fee_bps)."""
import os, json, gzip, collections
HERE = os.path.dirname(os.path.abspath(__file__))
M = {}
for l in gzip.open(os.path.join(HERE, "out", "vx_events_mine.jsonl.gz"), "rt"):
    r = json.loads(l); M[(r["m"], r["age"])] = r
for LAT, fn in (("35", "cv_claim_b05.json"), ("20", "cv_claim_b05.json"), ("50", "cv_claim_slow.json"), ("75", "cv_claim_slow.json")):
    sel = [M[(s["m"], s["age"])] for s in json.load(open(os.path.join(HERE, "out", fn)))[LAT]["sel"] if (s["m"], s["age"]) in M and LAT in M[(s["m"], s["age"])]["pnl"]]
    P = lambda r: r["pnl"][LAT]["c"] - 0.0016
    print(f"L{LAT} picks {len(sel)} total {sum(P(r) for r in sel):+.2f}")
    bins = [(0, 1.0001), (1.0001, 1.01), (1.01, 1.02), (1.02, 1.05), (1.05, 1.1), (1.1, 99)]
    print("  by entry price vs the post-sell price (px): " + " | ".join(
        f"[{lo},{hi if hi < 9 else 'inf'}) n {sum(1 for r in sel if lo <= r['px'][LAT] < hi)} {sum(P(r) for r in sel if lo <= r['px'][LAT] < hi):+.2f}" for lo, hi in bins))
    for g in (1.01, 1.02, 1.05):
        ok = [r for r in sel if r["px"][LAT] <= g]; fail = len(sel) - len(ok)
        print(f"  guard {g}: buys {len(ok)} total {sum(P(r) for r in ok):+.2f}; failed guarded {fail}: at 0.0002/fail {sum(P(r) for r in ok) - 0.0002 * fail:+.2f}, at 0.0008/fail {sum(P(r) for r in ok) - 0.0008 * fail:+.2f}")
fees = collections.Counter(round(r["fr"] * 1e4) for r in M.values() if r["cf"]); print("fee bps (fee+creator) on all dip sells:", fees.most_common(8))
