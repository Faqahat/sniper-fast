#!/usr/bin/env python3
# READ-ONLY, offline. Which exit pieces carry the profit (all SOL-quoted pump round trips of both wallets, measured from
# their own sells): piece PnL = net SOL of the sell tx - pro-rata all-in cost basis of the tokens it sold.
# Piece types: LIGHT = first sell <= 8 slots after the buy; TP = partial sell at a price >= every earlier own sell (rising);
# DD = partial sell below the previous own sell (falling); CLEAR+ / CLEAR- = final sell at / below entry; OPEN = cost of tokens
# never sold (still held at the end of the data, valued 0).
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
from analyze import pieces
for w in WALLETS:
    R = [r for r in json.load(open(f"{EXITS}/roundtrips_{w}.json"))["tokens"] if r["n_sells"]]
    for per in ("ledger", "all"):
        S = [r for r in R if per == "all" or r["period"] == per]
        g = collections.defaultdict(lambda: [0, 0.0, 0.0])
        for r in S:
            ps = pieces(r); tb = sum(l["tok"] for l in r["legs"] if l["side"] == "buy"); hi = 0
            for i, p in enumerate(ps):
                if i == 0 and p["dslot"] <= 8 and i < len(ps) - 1: k = "LIGHT"
                elif i == len(ps) - 1: k = "CLEAR+" if p["mult_pre"] >= 1 else "CLEAR-"
                elif p["mult_pre"] >= hi: k = "TP"
                else: k = "DD"
                hi = max(hi, p["mult_pre"])
                g[k][0] += 1; g[k][1] += p["piece_pnl"]; g[k][2] += p["tok"] / tb
            left = r["left_tok"]
            if left > 1: g["OPEN"][0] += 1; g["OPEN"][1] -= r["cost"] * left / tb; g["OPEN"][2] += left / tb
        tot = sum(v[1] for v in g.values())
        print(f"{w} [{per}] {len(S)} tokens, PnL {sum(r['pnl'] for r in S):+.2f} (pieces sum {tot:+.2f}):")
        for k in ("LIGHT", "TP", "DD", "CLEAR+", "CLEAR-", "OPEN"):
            v = g[k]; print(f"    {k:7} pieces {v[0]:5d}  PnL {v[1]:+7.2f} SOL  position-equivalents sold {v[2]:6.1f} ({v[2] / len(S):.0%} of all bought tokens)")
