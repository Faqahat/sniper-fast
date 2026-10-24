#!/usr/bin/env python3
"""verify_dip / sel_variants: the claim's OWN CV-selected trades (out/cv_claim_*.json, reproduced exactly) re-priced with my
independent replay variants (fixed selection), plus robustness: bootstrap of block totals, best-launch removal, per-tx cost.
usage: python3 -I -B sel_variants.py <my events> [cv json(s)...]"""
import sys, os, json, gzip, collections, random, statistics
HERE = os.path.dirname(os.path.abspath(__file__))
MY = sys.argv[1]
CVS = sys.argv[2:] or [os.path.join(HERE, "out", "cv_claim_b05.json"), os.path.join(HERE, "out", "cv_claim_slow.json")]
M = {}
for l in gzip.open(MY, "rt"):
    r = json.loads(l); M[(r["m"], r["age"])] = r
VARS = ["c", "t", "f0", "f150", "tf0", "tf150", "ns", "g", "h8"]
for fn in CVS:
    S = json.load(open(fn))
    for LAT, d in S.items():
        sel = d["sel"]; miss = [s for s in sel if (s["m"], s["age"]) not in M or LAT not in M[(s["m"], s["age"])]["pnl"]]
        ok = [s for s in sel if s not in miss]
        print(f"\n=== claim's CV selection at L={LAT} ms ({os.path.basename(fn)}): {len(sel)} trades, claim total {sum(s['pnl'] for s in sel):+.2f}; "
              f"re-priced by me: {len(ok)} (missing {len(miss)}, their claim pnl {sum(s['pnl'] for s in miss):+.2f})")
        for txc in (0.0008, 0.002, 0.003):
            cells = []
            for v in VARS:
                tot = sum(M[(s["m"], s["age"])]["pnl"][LAT][v] - 2 * txc for s in ok)
                cells.append(f"{v} {tot:+6.2f}")
            print(f"  per-tx cost {txc}: " + " | ".join(cells))
        # per block, variant c and t at 0.0008
        byb = collections.defaultdict(list)
        for s in ok: byb[s["b"]].append(s)
        print("  per block (c / t / tf0 at 0.0008): " + " ".join(
            f"b{b}:{sum(M[(s['m'], s['age'])]['pnl'][LAT]['c'] - 0.0016 for s in v):+.2f}/{sum(M[(s['m'], s['age'])]['pnl'][LAT]['t'] - 0.0016 for s in v):+.2f}/"
            f"{sum(M[(s['m'], s['age'])]['pnl'][LAT]['tf0'] - 0.0016 for s in v):+.2f}" for b, v in sorted(byb.items())))
        # diagnostics on the selected trades
        rows = [M[(s["m"], s["age"])] for s in ok]
        nshift = sum(1 for r in rows if r["info"][LAT]["s_true"] != r["info"][LAT]["s_in"])
        print(f"  our proxy arrival lands in a LATER slot than the last trade ahead (hold 1+ slot shorter in the claim): {nshift} of {len(rows)} ({nshift / len(rows):.0%})")
        ng = sum(1 for r in rows if r["info"][LAT]["grad"]); pg = sum(r["pnl"][LAT]["c"] - r["pnl"][LAT]["g"] for r in rows if r["info"][LAT]["grad"])
        print(f"  early sell at vsol >= 110 SOL / curve complete inside the hold: {ng} trades, they add {pg:+.2f} SOL vs holding to the exit")
        print(f"  curve kind: {dict(collections.Counter(r['kind'] for r in rows))}; seller tx has other legs: {sum(1 for r in rows if r['multileg'])} "
              f"(with a buy leg: {sum(1 for r in rows if r['multileg_buy'])}); launches with collector gaps (synthetic trades): {sum(1 for r in rows if r['ngap'])}")
        print(f"  ix of the sell: {dict(collections.Counter(r['ixn'] for r in rows))}")
        dn = sum(r["info"][LAT]["nd"] for r in rows); fnn = sum(r["info"][LAT]["nf"] for r in rows)
        print(f"  followers kept {fnn}, dropped by imputed slippage {dn}; trades ahead of us: mean {statistics.mean(r['ahead'][LAT] for r in rows):.2f}")
        # robustness: without the best 10 launches; bootstrap by launch within blocks
        per_m = collections.defaultdict(float)
        for s in ok: per_m[s["m"]] += M[(s["m"], s["age"])]["pnl"][LAT]["c"] - 0.0016
        best = sorted(per_m.items(), key=lambda kv: -kv[1])[:10]
        tot = sum(per_m.values())
        print(f"  total (c) {tot:+.2f} over {len(per_m)} launches; best 10 launches add {sum(v for _, v in best):+.2f} -> without them {tot - sum(v for _, v in best):+.2f}")
        rng = random.Random(7); B = 2000; tots = []; blk_pos = collections.Counter()
        bym = collections.defaultdict(lambda: collections.defaultdict(float))
        for s in ok: bym[s["b"]][s["m"]] += M[(s["m"], s["age"])]["pnl"][LAT]["c"] - 0.0016
        for _ in range(B):
            t = 0.0
            for b, mm in bym.items():
                vals = list(mm.values()); bt = sum(rng.choice(vals) for _ in vals); t += bt
                if bt > 0: blk_pos[b] += 1
            tots.append(t)
        tots.sort()
        print(f"  bootstrap (resample launches within each block, {B}x): total p2.5 {tots[int(0.025 * B)]:+.2f} p50 {tots[B // 2]:+.2f} p97.5 {tots[int(0.975 * B)]:+.2f}; "
              f"P(total <= 0) {sum(1 for x in tots if x <= 0) / B:.1%}; P(block > 0): " + " ".join(f"b{b} {blk_pos[b] / B:.0%}" for b in sorted(bym)))
