#!/usr/bin/env python3
# Claim 5: aggregates from v2_out/census_fifo.jsonl.gz (unique buys, per-wallet FIFO, MTM of what is left after 600 slots).
import json, gzip, collections, statistics
R = [json.loads(l) for l in gzip.open("/home/moiz/sniper/ops/overnight/verify_dip/v2_out/census_fifo.jsonl.gz", "rt")]
pl = lambda r: r["back"] + r["mtm"] - r["cost"]; pn = lambda r: pl(r) - r["txc"]
print(f"unique trip buys {len(R)} | SOL in {sum(r['cost'] for r in R):.0f} | P&L (FIFO, MTM) {sum(pl(r) for r in R):+.1f} | net of collector tx costs {sum(pn(r) for r in R):+.1f}"
      f" | fully sold within 600 slots {sum(1 for r in R if r['sold'] >= r['tok'])} | MTM part {sum(r['mtm'] for r in R):.1f} SOL")
W = collections.defaultdict(list)
for r in R: W[r["u"]].append(r)
print("by wallet activity (unique trip buys):")
for lo, hi in ((1, 10), (10, 30), (30, 100), (100, 10**6)):
    ws = [v for v in W.values() if lo <= len(v) < hi]; a = [sum(pl(r) for r in v) for v in ws]; b = [sum(pn(r) for r in v) for v in ws]
    real = [sum(pl(r) for r in v if r["mtm"] == 0) for v in ws]
    print(f"  {lo:3d}-{hi:<7d} wallets {len(ws):5d} trips {sum(len(v) for v in ws):6d} | P&L {sum(a):+7.1f} ({sum(1 for x in a if x > 0) / len(a):.0%} pos) | net of tx {sum(b):+7.1f} ({sum(1 for x in b if x > 0) / len(b):.0%} pos) | closed-only trips {sum(real):+7.1f}")
print("by delay (ms, proxy):")
for lo, hi in ((0, 10), (10, 25), (25, 40), (40, 60), (60, 100), (100, 151)):
    g = [r for r in R if lo <= r["dt"] < hi]; p = sum(pl(r) for r in g); v = sum(r["cost"] for r in g)
    cl = [r for r in g if r["mtm"] == 0]; pc = sum(pl(r) for r in cl)
    srt = sorted((pn(r) for r in g), reverse=True)
    print(f"  {lo:3d}-{hi:<4d} n {len(g):5d} | P&L {p:+7.1f} ({p / v:+.2%}) | net of tx {sum(pn(r) for r in g):+7.1f} | w/o top-20 trades {sum(srt[20:]):+7.1f} | closed trips only n {len(cl)} {pc:+7.1f} ({pc / max(sum(r['cost'] for r in cl), 1):+.2%})")
big = [v for v in W.values() if len(v) >= 100]
print(f">=100-trip wallets: {len(big)} | trips {sum(len(v) for v in big)} | P&L {sum(pl(r) for v in big for r in v):+.1f} | net of tx {sum(pn(r) for v in big for r in v):+.1f} | positive net {sum(1 for v in big if sum(pn(r) for r in v) > 0)}")
for U in ("DYXDDrZC", "HkQ7hMjy", "haqqiUUX", "sssssDdM", "ETwEAQPL", "5mWe9kLZ", "ssssswdk"):
    v = next((v for u, v in W.items() if u.startswith(U)), [])
    print(f"  {U}: unique trips {len(v)} P&L {sum(pl(r) for r in v):+.2f} net {sum(pn(r) for r in v):+.2f} | median delay {statistics.median(r['dt'] for r in v):.0f} ms")
# persistence R1 -> R2 on unique trips, net of tx
p1 = {u: [r for r in v if r["run"] == "R1"] for u, v in W.items()}; p2 = {u: [r for r in v if r["run"] == "R2"] for u, v in W.items()}
c1 = [u for u in W if len(p1[u]) >= 30]
for name, sel in (("R1-positive", lambda u: sum(pn(r) for r in p1[u]) > 0), ("R1-negative", lambda u: sum(pn(r) for r in p1[u]) <= 0)):
    us = [u for u in c1 if sel(u)]; r2 = [sum(pn(r) for r in p2[u]) for u in us if p2[u]]
    print(f"persistence {name}: {len(us)} wallets (>=30 R1 trips), R1 net {sum(sum(pn(r) for r in p1[u]) for u in us):+.1f} | in R2: {len(r2)} active, net {sum(r2):+.1f}, {sum(1 for x in r2 if x > 0) / max(len(r2), 1):.0%} positive")
