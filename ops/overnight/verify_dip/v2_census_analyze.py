#!/usr/bin/env python3
# Claim 5 analysis of v2_out/census_v2.jsonl.gz (from v2_census.py). Local only.
#  M0 = the census's own method (no-sell trips dropped, unsold remainder of partial trips valued at 0)
#  M1 = closed part only: back - cost x sold/bought (trips with a sell)
#  M2 = mark-to-market, ALL trips: back + value of the unsold remainder at the window end - cost (no-sell trips included)
#  M2n = M2 minus real tx costs (collector fee + tips of the buy and of the sells used; failed attempts NOT included)
import json, gzip, collections, statistics, random
R = [json.loads(l) for l in gzip.open("/home/moiz/sniper/ops/overnight/verify_dip/v2_out/census_v2.jsonl.gz", "rt")]
def m0(r): return None if r["nosell"] else r["back"] - r["cost"]
def m1(r): return None if r["nosell"] else r["back"] - r["cost"] * r["sold"] / r["tok"]
def m2(r): return r["back"] + r["remv"] - r["cost"]
def m2n(r): return m2(r) - r["txc"]
M = {"M0 census": m0, "M1 closed part": m1, "M2 mark-to-market": m2, "M2n MTM - tx costs": m2n}
def tot(rows, f): v = [f(r) for r in rows]; v = [x for x in v if x is not None]; return sum(v), len(v)
print(f"trips {len(R)} | no sell within 600 slots {sum(r['nosell'] for r in R)} | partial {sum(1 for r in R if not r['nosell'] and not r['full'])} | full {sum(r['full'] for r in R)}")
print(f"wallet already held the token before the buy (pre > 0): {sum(1 for r in R if r['pre'] > 0)} trips ({sum(1 for r in R if r['pre'] > 0) / len(R):.1%})")
# one sell consumed by several trips of the same wallet (double counting)
use = collections.defaultdict(float); stok = {}
for r in R:
    for s, sl, tk in r["sells"]: use[(r["u"], s)] += tk
dbl = collections.Counter()
for r in R:
    for s, sl, tk in r["sells"]: dbl[(r["u"], s)] += 1
print(f"sells used by >1 trip of the same wallet: {sum(1 for v in dbl.values() if v > 1)} of {len(dbl)}")
for name, f in M.items():
    t, n = tot(R, f); print(f"{name:20s}: trips {n:6d} P&L {t:+8.1f}")
W = collections.defaultdict(list)
for r in R: W[r["u"]].append(r)
print("\nby wallet activity (trips with a sell, as the census counts them):")
for lo, hi in ((1, 10), (10, 30), (30, 100), (100, 10**6)):
    ws = [v for v in W.values() if lo <= sum(1 for r in v if not r["nosell"]) < hi]
    line = f"  {lo:3d}-{hi:<7d} wallets {len(ws):5d}"
    for name, f in M.items():
        ps = [tot(v, f)[0] for v in ws]; line += f" | {name.split()[0]} {sum(ps):+7.1f} ({sum(1 for p in ps if p > 0) / max(len(ps), 1):.0%} pos)"
    print(line)
print("\nby delay after the sell (ms, proxy):")
for lo, hi in ((0, 10), (10, 25), (25, 40), (40, 60), (60, 100), (100, 151)):
    g = [r for r in R if lo <= r["dt"] < hi]
    print(f"  {lo:3d}-{hi:<4d} n {len(g):5d}" + "".join(f" | {name.split()[0]} {tot(g, f)[0]:+7.1f}" for name, f in M.items())
          + f" | no-sell {sum(r['nosell'] for r in g)} partial {sum(1 for r in g if not r['nosell'] and not r['full'])} | SOL in {sum(r['cost'] for r in g):.0f}")
# the 0-10 ms band: who
g = [r for r in R if r["dt"] < 10]; Wg = collections.defaultdict(list)
for r in g: Wg[r["u"]].append(r)
print("\n0-10 ms band, top wallets by trips: wallet, trips, M0, M2, M2n, mean size")
for u, v in sorted(Wg.items(), key=lambda kv: -len(kv[1]))[:8]:
    print(f"  {u[:10]} {len(v):5d} {tot(v, m0)[0]:+7.2f} {tot(v, m2)[0]:+7.2f} {tot(v, m2n)[0]:+7.2f} {statistics.mean(r['cost'] for r in v):.2f}")
print("0-10 ms band, partial/no-sell trips: largest M0 losses and their M2 value:")
for r in sorted((r for r in g if not r["full"]), key=lambda r: (m0(r) or 0))[:6]:
    print(f"  {r['u'][:10]} cost {r['cost']:.3f} back {r['back']:.3f} sold {r['sold'] / r['tok']:.0%} remv {r['remv']:.3f} pre {r['pre'] > 0} nosell {r['nosell']}")
# delay bands within the same wallets (wallets active in >= 3 bands with >= 20 trips each)
print("\nwithin-wallet: per-trip mean M2n by delay band, wallets with >=20 trips in a band:")
bands = ((0, 10), (10, 25), (25, 40), (40, 60), (60, 100), (100, 151))
for u, v in sorted(W.items(), key=lambda kv: -len(kv[1]))[:12]:
    cells = []
    for lo, hi in bands:
        b = [m2n(r) for r in v if lo <= r["dt"] < hi]
        cells.append(f"{statistics.mean(b):+.4f}({len(b)})" if len(b) >= 20 else "      -     ")
    print(f"  {u[:10]} " + " ".join(cells))
# persistence: wallets ranked on R1, evaluated on R2 (M2n)
print("\nskill persistence (M2n): wallets with >=30 trips in R1, their R2 result")
p1 = {u: [r for r in v if r["run"] == "R1"] for u, v in W.items()}; p2 = {u: [r for r in v if r["run"] == "R2"] for u, v in W.items()}
c1 = [u for u in W if len(p1[u]) >= 30]
pos1 = [u for u in c1 if tot(p1[u], m2n)[0] > 0]; neg1 = [u for u in c1 if tot(p1[u], m2n)[0] <= 0]
for name, us in (("R1-positive", pos1), ("R1-negative", neg1)):
    r2 = [tot(p2[u], m2n)[0] for u in us if p2[u]]
    print(f"  {name}: {len(us)} wallets, R1 {sum(tot(p1[u], m2n)[0] for u in us):+.1f} | active in R2 {len(r2)}, R2 total {sum(r2):+.1f}, R2 positive {sum(1 for x in r2 if x > 0) / max(len(r2), 1):.0%}")
# >=100-trip group, net of tx costs
big = [v for v in W.values() if sum(1 for r in v if not r["nosell"]) >= 100]
print(f"\n>=100-trip wallets: {len(big)} | trips {sum(len(v) for v in big)} | M0 {sum(tot(v, m0)[0] for v in big):+.1f} | M2 {sum(tot(v, m2)[0] for v in big):+.1f} | tx costs {sum(r['txc'] for v in big for r in v):.1f} | M2n {sum(tot(v, m2n)[0] for v in big):+.1f}")
for U in ("DYXDDrZC", "HkQ7hMjy", "haqqiUUX"):
    v = next((v for u, v in W.items() if u.startswith(U)), [])
    print(f"  {U}: trips {len(v)} (no-sell {sum(r['nosell'] for r in v)}, partial {sum(1 for r in v if not r['nosell'] and not r['full'])}, pre-held {sum(1 for r in v if r['pre'] > 0)})"
          f" M0 {tot(v, m0)[0]:+.2f} M1 {tot(v, m1)[0]:+.2f} M2 {tot(v, m2)[0]:+.2f} tx {sum(r['txc'] for r in v):.2f} M2n {tot(v, m2n)[0]:+.2f} | median tx cost/trip {statistics.median(r['txc'] for r in v):.5f}")
