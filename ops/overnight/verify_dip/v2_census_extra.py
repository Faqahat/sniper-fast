#!/usr/bin/env python3
# Claim 5 extras on v2_out/census_v2.jsonl.gz: (1) sells attributed to more than one trip of the same wallet (over-attribution);
# (2) full-trip-only P&L by delay band and by wallet activity (no valuation assumption at all); (3) concentration.
import json, gzip, collections, statistics
R = [json.loads(l) for l in gzip.open("/home/moiz/sniper/ops/overnight/verify_dip/v2_out/census_v2.jsonl.gz", "rt")]
take = collections.defaultdict(int); stok = {}; sol_of = {}
for r in R:
    for s, sl, tk, st, c in r["sells"]: take[(r["u"], s)] += tk; stok[(r["u"], s)] = st
over = {k: take[k] - stok[k] for k in take if take[k] > stok[k]}
print(f"(wallet, sell) pairs {len(take)} | over-attributed (sum of takes > tokens sold) {len(over)} | excess tokens share {sum(over.values()) / sum(stok.values()):.2%}")
# P&L of trips whose sells are over-attributed
ov_trips = [r for r in R if any((r["u"], s[0]) in over for s in r["sells"])]
print(f"trips touching an over-attributed sell: {len(ov_trips)}, their census P&L {sum(r['back'] - r['cost'] for r in ov_trips):+.1f}")
F = [r for r in R if r["full"]]
print(f"\nFULL trips only: {len(F)} trips, P&L {sum(r['back'] - r['cost'] for r in F):+.1f} on {sum(r['cost'] for r in F):.0f} SOL; minus collector tx costs {sum(r['back'] - r['cost'] - r['txc'] for r in F):+.1f}")
for lo, hi in ((0, 10), (10, 25), (25, 40), (40, 60), (60, 100), (100, 151)):
    g = [r for r in F if lo <= r["dt"] < hi]; p = sum(r["back"] - r["cost"] for r in g); v = sum(r["cost"] for r in g)
    srt = sorted((r["back"] - r["cost"] for r in g), reverse=True)
    pn = sum(r["back"] - r["cost"] - r["txc"] for r in g)
    print(f"  delay {lo:3d}-{hi:<4d} n {len(g):5d} P&L {p:+7.1f} ({p / v:+.2%} of {v:.0f} SOL) | net of tx {pn:+7.1f} | top-20 trades {sum(srt[:20]):+6.1f} | without top-20 {p - sum(srt[:20]):+6.1f} | median {statistics.median(srt):+.4f}")
W = collections.defaultdict(list)
for r in R: W[r["u"]].append(r)
for lo, hi in ((1, 10), (10, 30), (30, 100), (100, 10**6)):
    ws = [v for v in W.values() if lo <= sum(1 for r in v if not r["nosell"]) < hi]
    ps = [sum(r["back"] - r["cost"] for r in v if r["full"]) for v in ws]; pn = [sum(r["back"] - r["cost"] - r["txc"] for r in v if r["full"]) for v in ws]
    print(f"  wallets {lo:3d}-{hi:<7d}: {len(ws):5d} | full-trip P&L {sum(ps):+7.1f} ({sum(1 for p in ps if p > 0) / len(ps):.0%} pos) | net of tx {sum(pn):+7.1f} ({sum(1 for p in pn if p > 0) / len(pn):.0%} pos)")
