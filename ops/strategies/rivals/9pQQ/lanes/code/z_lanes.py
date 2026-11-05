#!/usr/bin/env python3
"""Collect all LANES results into lanes/lanes.json."""
import json, pickle, collections, glob, os, numpy as np
L = "/home/moiz/sniper/ops/strategies/rivals/9pQQ/lanes"; D = "/home/moiz/sniper-data/rivals/9pQQ/lanes"
out = {"wallet": "9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN", "written": "2026-11-03", "times": "PKT"}
R = pickle.load(open(f"{D}/decjoin.pkl", "rb")); B = [r for r in R if r["kind"] == "buy" and "trip" in r]
C = collections.Counter(("EXACT" if r["cls"] != "PHANTOM" else "PHANTOM", "first" if r["trip"]["k_prev"] == 0 else "re") for r in B)
out["separation_pricing_source"] = {"rule": "BuyExactQuoteInV3 min_tokens_out = E_buy(state)/1.15 exactly (1e-10) when priced on a landed curve state",
    "sampled_buys": len(B), "table": {f"{a}|{b}": v for (a, b), v in C.items()},
    "agreement": round((C[("EXACT", "first")] + C[("PHANTOM", "re")]) / sum(C.values()), 4),
    "fails": dict(collections.Counter(r["cls"] for r in R if r["kind"] == "fail"))}
for f in ("lane_table.json",):
    out["lane_table"] = json.load(open(f"{D}/{f}"))
for f in ("entry_gbdt_on.json", "exit_gbdt.json", "calib.json", "replay_exit_v3.json"):
    if os.path.exists(f"{L}/{f}"): out[f[:-5]] = json.load(open(f"{L}/{f}"))
for f in glob.glob(f"{L}/replay_entry_x*.json"): out[os.path.basename(f)[:-5]] = json.load(open(f))
out["pending_flow_test"] = {"hypothesis": "TRK internal state = landed state + not-yet-landed trades", "phantom_buys": 662,
  "corr(dec_dev, later landed outside flow same slot / +1 / +3 slots)": [-0.057, -0.023, 0.006],
  "corr(dec_dev, failed outside buys before / after)": [-0.234, -0.247], "verdict": "rejected: the state does not lead landed flow; around failed-buy pumps it LAGS (dec price below landing, median -3.6%); offsets are not constant per token"}
out["tip_recipe_check"] = {"result": "identical on every landed buy/sell, all 5 days, NEW and TRK, before and after the 10-31 00:10 PKT redeploy: buy CU 1,500,001 x 130,000 + Astralane 1,000,000 + Jito 17,500; sell CU 1,500,001 x 80,000 (200,000 on rare SellV2) + Astralane 100,000 + Jito 17,500; Jito account uniform over 8"}
out["instances_10_31"] = {"window_pkt": "10-31 06:30-10:00 (casebook: to 10:50)", "multi_trip_tokens": 209, "single_size": 204, "handover_0.48_to_0.70": 5, "reverse": 0,
  "shared_blockhash_across_sizes": "yes (4 pairs within 1-2 slots in the 225-tx dense sample)", "pricing_concordance_both_sizes": "117/117", "msol_per_trip": [13.7, 13.6]}
json.dump(out, open(f"{L}/lanes.json", "w"), indent=1, default=float); print("written", list(out))
