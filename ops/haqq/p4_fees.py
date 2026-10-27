#!/usr/bin/env python3
# haqq SEND PATHS, part 4 (local): fee tier of every landed / failed haqq tx (priority fee = fee - 5000 lamports) by path, size, kind.
import sys, json, collections, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/haqq"); import h_lib as H
R = json.load(open(f"{H.OUT}/paths1.json"))
tier = lambda f: "low (~17k)" if f < 50000 else "high (~125k)"
print("kind x fee tier:")
for k in ("buy", "sell", "fail_buy"):
    S = [r for r in R if r["kind"] == k]
    c = collections.Counter(tier(r["fee"]) for r in S)
    print(f"   {k:9s} n {len(S):6d}: " + ", ".join(f"{a} {b} ({100 * b / len(S):.0f}%)" for a, b in c.most_common()))
print("\nlanded buys: path x fee tier (row %):")
B = [r for r in R if r["kind"] == "buy"]
for sv, n in collections.Counter(r["svc"] for r in B).most_common(7):
    s = [r for r in B if r["svc"] == sv]; c = collections.Counter(tier(r["fee"]) for r in s)
    print(f"   {sv:10s} n {n:6d}: " + ", ".join(f"{a} {100 * b / n:.0f}%" for a, b in c.most_common()))
print("\nbuys by size: landed fee tier, and failed (6042) share per tier")
F = [r for r in R if r["kind"] == "fail_buy"]
for lab, lo, hi in (("<0.05", 0, 0.05), ("0.05-0.5", 0.05, 0.5), (">=0.5", 0.5, 99)):
    s = [r for r in B if lo <= r["size"] < hi]
    c = collections.Counter(tier(r["fee"]) for r in s)
    print(f"   {lab:9s} landed n {len(s)}: " + ", ".join(f"{a} {100 * b / len(s):.0f}%" for a, b in c.most_common()))
print(f"   failed buys n {len(F)}: " + ", ".join(f"{a} {b} ({100 * b / len(F):.0f}%)" for a, b in collections.Counter(tier(r['fee']) for r in F).most_common()))
lo_ok = sum(1 for r in B if r["fee"] < 50000); hi_ok = len(B) - lo_ok; lo_f = sum(1 for r in F if r["fee"] < 50000); hi_f = len(F) - lo_f
print(f"   6042 share of landed attempts: low tier {lo_f / (lo_f + lo_ok):.0%} ({lo_f}/{lo_f + lo_ok}), high tier {hi_f / (hi_f + hi_ok):.0%} ({hi_f}/{hi_f + hi_ok})")
print("\nCU limit (buys / sells) median:", np.median([r["cul"] for r in B]), np.median([r["cul"] for r in R if r["kind"] == "sell"]),
      "| CU used median:", np.median([r["cu"] for r in B]), np.median([r["cu"] for r in R if r["kind"] == "sell"]))
print("priority fee lamports (fee - 5000) median: high-tier buys", np.median([r["fee"] - 5000 for r in B if r["fee"] >= 50000]), "low-tier buys", np.median([r["fee"] - 5000 for r in B if r["fee"] < 50000]),
      "sells", np.median([r["fee"] - 5000 for r in R if r["kind"] == "sell"]))
