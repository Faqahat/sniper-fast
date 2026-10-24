#!/usr/bin/env python3
# Claim 6: the 2-slot model's out-of-fold picks (v2_out/oof_dw_exit2.jsonl, all exit variants stored per pick) priced with every exit,
# under the claim's follower model ("H") and with follower slippage failures limited to followers arriving <= DW ms after our buy
# ("HwDW"; w0 = no follower ever fails). Unguarded and 2% guard. Same trades for every exit -> pure exit effect.
import json, collections
R = [json.loads(l) for l in open("/home/moiz/sniper/ops/overnight/verify_dip/v2_out/oof_dw_exit2.jsonl")]
H = ("2", "4", "8", "10", "20", "40", "80"); V = ("", "w1000", "w400", "w0")
for LAT in ("35", "50", "75"):
    S = [r for r in R if r["LAT"] == LAT and r["f"] >= r["thr"]]
    print(f"\nLAT {LAT}: {len(S)} picks (2-slot model, top 5%)   rows = exit slots; columns = follower model (unguarded / 2% guard)")
    print("   exit  " + "".join(f"{('claim' if v == '' else v):>20s}" for v in V))
    for h in H:
        cells = []
        for v in V:
            k = h + v; vals = [r["pall"].get(k) for r in S]
            if any(x is None for x in vals): cells.append(f"{'-':>20s}"); continue
            g = sum((r["pall"][k] if r["px"] <= 1.02 else -0.0002) for r in S)
            cells.append(f"{sum(vals):+9.2f} / {g:+7.2f} ")
        print(f"   {h:>4s} " + "".join(cells))
