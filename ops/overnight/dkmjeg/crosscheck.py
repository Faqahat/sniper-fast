#!/usr/bin/env python3
# READ-ONLY, offline: ledger (ground truth) vs the collector-window numbers in wallets.json (R1 10-21 22:07 -> 10-22 13:00,
# R2 10-22 15:43 -> 10-23 00:35 by launch time): tokens, PnL, failed-only attempts and their cost.
import json, collections
L = json.load(open("/home/moiz/sniper/ops/overnight/dkmjeg/ledger.json")); T = L["tokens"]
C = json.load(open("/home/moiz/sniper/ops/overnight/dkmjeg/coll.json"))
WIN = {"R1": (1792620447, 1792674000), "R2": (1792683802, 1792729999)}
for run, (a, b) in WIN.items():
    ms = {m for m, v in C.items() if v["run"] == run}
    tb = [x for m, x in T.items() if m in ms and x["buys"]]
    tn = [x for m, x in T.items() if m in ms and not x["buys"]]
    sq = [x for x in tb if x["quote"] == "SOL"]
    print(f"{run}: ledger tokens bought {len(tb)} (SOL-quoted {len(sq)}) -> {sum(x['pnl'] for x in tb):+.2f} SOL (SOL-quoted {sum(x['pnl'] for x in sq):+.2f}) | "
          f"never filled {len(tn)} -> {sum(x['pnl'] for x in tn):+.2f} | all {sum(x['pnl'] for x in tb) + sum(x['pnl'] for x in tn):+.2f}")
W = json.load(open("/home/moiz/sniper/ops/overnight/wallets/wallets.json"))["dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK"]
print("wallets.json (collector):", {k: (W[k]["n"], W[k]["pnl"], W[k]["fail_cost"]) for k in ("R1", "R2", "all")}, "n_fail_only", W["n_fail_only"], "fail_cost", W["fail_cost"])
