#!/usr/bin/env python3
# HOW A WALLET TRADES (read-only, offline): for each token a wallet traded (positions.json from fetch_wallet.py), rebuild
# the exact on-chain trade list from the collector and describe its first buy: how long after the launch, how many
# outside buyers / sells came before, its price vs the post-bundle price and vs the peak before it, whether it bought
# right behind a sell in the same block, how long it held, and its real SOL result; then results by type of entry.
# usage: python3 wallet_entries.py <wallet> <positions.json> <launches.jsonl,> <phaseA dirs,>
import sys, json, gzip, glob, zlib, collections
W, POS, LJS, PAS = sys.argv[1:5]
pos = json.load(open(POS))
L = {}
for p in LJS.split(","):
    for l in open(p):
        try: c = json.loads(l); L.setdefault(c["mint"], c)
        except Exception: pass
ms = [m for m in pos if m in L and pos[m]["buys"]]
def bucket(m): return zlib.crc32(m.encode()) % 256
byb = collections.defaultdict(set)
for m in ms: byb[bucket(m)].add(m)
TR = collections.defaultdict(list)
for b, s in byb.items():
    seen = set()
    for pa in PAS.split(","):
        for f in glob.glob(f"{pa}/b{b:03d}/*.jsonl.gz"):
            try:
                for line in gzip.open(f, "rt"):
                    if line[2] != "T": continue
                    r = json.loads(line)
                    if r[1] not in s or (r[5], r[13]) in seen: continue
                    seen.add((r[5], r[13])); TR[r[1]].append((r[2], r[3], r[13], r[5], r[14], r[15] == 1, r[16] / 1e9, r[18], r[19]))
            except (EOFError, OSError, zlib.error): pass
rows = []
for m in ms:
    tr = sorted(TR.get(m, []))
    if not tr: continue
    c = L[m]; S = c["slot"]; ci = c.get("idx"); prev = ci; gi = 0; bus = set(); creator = c.get("creator") or c.get("user")
    for k, t in enumerate(tr):
        if t[3] == c.get("sig"): gi = k + 1; continue
        if t[0] == S and t[1] in (prev, prev + 1) and t[5]: bus.add(t[4]); prev = t[1]; gi = k + 1
        elif t[0] == S and t[1] > prev + 1: break
        elif t[0] > S: break
    if gi == 0 or not tr[gi - 1][8]: continue
    P0 = tr[gi - 1][7] / tr[gi - 1][8]; px = [(t[7] / t[8]) / P0 if t[8] else None for t in tr]
    wb = [k for k, t in enumerate(tr) if t[4] == W and t[5]]; ws = [k for k, t in enumerate(tr) if t[4] == W and not t[5]]
    if not wb: continue
    k = wb[0]; before = [p for p in px[gi - 1:k] if p]; peak = max(before) if before else 1.0
    ls = max((j for j in range(k) if not tr[j][5]), default=None)
    rows.append(dict(m=m, delay_s=(tr[k][0] - S) / 5, ahead=sum(1 for t in tr[gi:k] if t[5] and t[4] not in bus and t[4] != creator),
                     sells_before=sum(1 for t in tr[gi:k] if not t[5]), entry_vs_bundle=px[k - 1] or 1.0, entry_vs_peak=(px[k - 1] or 1.0) / peak - 1,
                     after_sell_same_block=ls is not None and tr[ls][0] == tr[k][0], curve=tr[k][7] / 1e9, nbuys=len(wb),
                     hold_s=((tr[ws[-1]][0] - tr[k][0]) / 5) if ws else None, exit_vs_entry=((px[ws[-1]] or 0) / (px[k] or 1) - 1) if ws else None,
                     max_after=(max([p for p in px[k:k + 1500] if p] or [1]) / (px[k] or 1) - 1), pnl=pos[m]["dsol"],
                     dev=sum(t[6] for t in tr if t[3] == c.get("sig") and t[5]), bundle=len(bus), buy_sol=sum(tr[j][6] for j in wb)))
print(f"wallet tokens {len(pos)} | inside our collection {len(ms)} | with the full price path {len(rows)}")
q = lambda v, p: sorted(v)[int(p * (len(v) - 1))]
for kk, lab in (("delay_s", "seconds after launch when it first buys"), ("ahead", "outside buyers before it"), ("sells_before", "sells before it"),
                ("entry_vs_bundle", "its price vs the price right after the bundle"), ("entry_vs_peak", "its price vs the peak before it"),
                ("curve", "curve size when it buys (SOL)"), ("buy_sol", "SOL it puts in per token"), ("hold_s", "seconds from first buy to last sell"),
                ("exit_vs_entry", "price at its last sell vs its first buy"), ("max_after", "best price in the 5 min after its buy vs its buy"), ("dev", "dev buy (SOL)")):
    v = [r[kk] for r in rows if r[kk] is not None]
    if v: print(f"  {lab:48} p10 {q(v, .1):+.3f}  p25 {q(v, .25):+.3f}  median {q(v, .5):+.3f}  p75 {q(v, .75):+.3f}  p90 {q(v, .9):+.3f}")
n = max(len(rows), 1)
print(f"  buys right behind a sell in the same block: {sum(r['after_sell_same_block'] for r in rows) / n:.0%} | token has a bundle {sum(r['bundle'] > 0 for r in rows) / n:.0%} | buys more than once {sum(r['nbuys'] > 1 for r in rows) / n:.0%}")
for lab, f in (("first buy within 10 s", lambda r: r["delay_s"] <= 10), ("10-60 s", lambda r: 10 < r["delay_s"] <= 60), ("after 60 s", lambda r: r["delay_s"] > 60),
               ("one buy", lambda r: r["nbuys"] == 1), ("buys again (adds more)", lambda r: r["nbuys"] > 1), ("held < 30 s", lambda r: (r["hold_s"] or 0) < 30),
               ("held 30 s - 3 min", lambda r: 30 <= (r["hold_s"] or 0) < 180), ("held 3 min+", lambda r: (r["hold_s"] or 0) >= 180),
               ("bought into a run-up (1.3x+ the bundle price)", lambda r: r["entry_vs_bundle"] >= 1.3), ("bought a dip (20%+ under the peak)", lambda r: r["entry_vs_peak"] <= -0.2),
               ("right behind a sell, same block", lambda r: r["after_sell_same_block"])):
    v = [r["pnl"] for r in rows if f(r)]
    if v: print(f"  {lab:46} n={len(v):3} total {sum(v):+.3f} SOL wins {sum(x > 0 for x in v)} ({sum(x > 0 for x in v) / len(v):.0%})")
json.dump(rows, open(POS.replace("positions.json", "entries.json"), "w"))
