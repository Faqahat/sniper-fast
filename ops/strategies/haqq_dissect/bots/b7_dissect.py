#!/usr/bin/env python3
"""BOTS step 7 (read-only): dissection tables per bot (247, 248; 244 / 226 for contrast), MEASURED from the tape + code-matched lots.
 - landing: dump -> his buy (ms, slots, same slot), outside trades ahead of him (k), price paid vs post-dump (pr), size
 - exits: hold (s, slots), sells per lot, hold-slot menu (most common hold lengths), the sell vs the follower wave (time since the
   last outside buy when he sells; share of sells within 1 s of an outside buy), his return at the sell vs the best value he could
   have had during the hold (TP behaviour) - values from the exact replay of his own lot (b4 'his' entry, validated to his realized)
 - economics: lot net by k ahead, by hold, by seller type, by token age, per day
 - non-dump lots (no >= 5 % outside drop within 2 slots before): what came before them
Out: bots/b7.txt"""
import sys, pickle, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos")
import xlib as X
from plib import boot_sum, Out
OUT = "/home/moiz/sniper-data/haqq_dissect/bots"


def main():
    P = Out(f"{OUT}/b7.txt")
    rows = pickle.load(open(f"{OUT}/b1.pkl", "rb"))
    Z = pickle.load(open(f"{OUT}/b4_res.pkl", "rb")); meta, res = Z["meta"], Z["res"]
    hisk = {}; hispr = {}
    for i, m in meta.items():
        if m["kind"] == "lot" and res.get(i): hisk[m["li"]] = res[i][0]["k"]; hispr[m["li"]] = res[i][0]["pr"]
    codes = pickle.load(open(f"{OUT}/hcodes.pkl", "rb"))
    R, MI, span, CC = X.tape(); H = MI["who"]["haqq"]; ours = (MI["who"]["FRA"], MI["who"]["AMS"])
    ok = lambda r: r["usable"] and not r["gap"]
    P("# Bots dissected (MEASURED, code-matched lots, usable hours, non-mayhem, 10-22 03:07 -> 10-28 01:12 PKT)")
    # ---------------- landing / size / limit
    P("\n## 1. Landing, position, price, size (dump-reactive lots in the dv8 universe)")
    P("| code | lots | size p50 (p10..p90) | dump->buy ms p25/50/75 | same slot | trades ahead k p25/50/75/90 | k=0 | price vs post-dump p50 / p90 | > 1.05x |")
    P("|---|---|---|---|---|---|---|---|---|")
    for c in (247, 248, 244, 226):
        v = [r for r in rows if r["code"] == c and ok(r) and r["dump"] and r["u"] is not None]
        k = np.array([hisk[r["li"]] for r in v if r["li"] in hisk]); pr = np.array([hispr[r["li"]] for r in v if r["li"] in hispr])
        ms = np.array([r["d_ms"] for r in v]); sz = np.array([r["size"] for r in v])
        P(f"| {c} | {len(v):,} | {np.median(sz):.2f} ({np.percentile(sz, 10):.2f}..{np.percentile(sz, 90):.2f}) | " + " / ".join(f"{x:.0f}" for x in np.percentile(ms, [25, 50, 75]))
          + f" | {100 * np.mean([r['d_slots'] == 0 for r in v]):.0f}% | " + (" / ".join(f"{x:.0f}" for x in np.percentile(k, [25, 50, 75, 90])) if len(k) else "-")
          + (f" | {100 * np.mean(k == 0):.0f}% | {np.median(pr):.3f} / {np.percentile(pr, 90):.3f} | {100 * np.mean(pr > 1.05):.0f}% |" if len(k) else " | - | - | - |"))
    # ---------------- exits
    P("\n## 2. Exits: hold, sells per lot, hold-slot menu, sell vs the follower wave (all lots of the code)")
    P("| code | lots | hold s p10/25/50/75/90 | 1 sell | top hold lengths (slots: share) | sells with an outside buy < 1 s before | median ms since last outside buy at his sell | his sell value vs best during hold p50 |")
    P("|---|---|---|---|---|---|---|---|")
    for c in (247, 248, 244, 226):
        v = [r for r in rows if r["code"] == c and ok(r) and r["hold"] is not None]
        h = np.array([r["hold"] for r in v])
        hs = collections.Counter(int(round(x / 0.212)) for x in h)
        top = ", ".join(f"{k}: {100 * n / len(v):.0f}%" for k, n in hs.most_common(6))
        # wave: sample up to 3000 single-sell lots
        rng = np.random.default_rng(1); vv = [r for r in v if r["nsell"] == 1 and r["mi"] in span]
        vv = [vv[i] for i in rng.choice(len(vv), min(3000, len(vv)), replace=False)]
        since = []; best = []
        for r in vv:
            a, b = span[r["mi"]]; Xr = R[a:b]; cc = CC[a:b]
            outside = ~np.isin(Xr["user"], (H,) + ours)
            t0, t1 = r["cc"], r["close_cc"]
            ob = outside & Xr["buy"].astype(bool) & (cc < t1) & (cc > t0)
            since.append((t1 - cc[ob].max()) if ob.any() else np.nan)
            # value path of his tokens during the hold (approx: curve state after each row, his tokens, net of fee)
            w = (cc > t0) & (cc < t1)
            if w.any():
                vs = Xr["vsol"][w] / 1e9; vt = Xr["vtok"][w].astype(np.float64); tok = r["tok"]
                val = (vs - vs * vt / (vt + tok)) * (1 - X.FEE)
                best.append(r["out"] / max(val.max(), 1e-9))
        since = np.array(since)
        P(f"| {c} | {len(v):,} | " + " / ".join(f"{x:.1f}" for x in np.percentile(h, [10, 25, 50, 75, 90])) + f" | {100 * np.mean([r['nsell'] == 1 for r in v]):.0f}% | {top} | "
          f"{100 * np.nanmean(since < 1000):.0f}% | {np.nanmedian(since):.0f} | {np.median(best):.3f} |")
    # ---------------- economics
    def econ(title, key, bins, labels=None):
        P(f"\n## 3. Economics by {title} (dump-reactive lots in the universe; net after his costs, mSOL/lot; D0..D6 net)")
        P("| code | bucket | lots | net SOL [90%] | mSOL/lot | win | D0..D6 net | days > 0 |"); P("|---|---|---|---|---|---|---|---|")
        for c in (247, 248):
            v = [r for r in rows if r["code"] == c and ok(r) and r["dump"] and r["u"] is not None and r["li"] in hisk]
            for bi, b in enumerate(bins):
                w = [r for r in v if b(key(r))]
                if len(w) < 30: continue
                x = [r["net"] for r in w]; lo, hi = boot_sum(x); pdn = [sum(r["net"] for r in w if r["day"] == d) for d in range(7)]
                P(f"| {c} | {labels[bi]} | {len(w):,} | {sum(x):+.2f} [{lo:+.1f}..{hi:+.1f}] | {1000 * np.mean(x):+.2f} | {100 * np.mean([y > 0 for y in x]):.0f}% | "
                  + " ".join(f"{p:+.1f}" for p in pdn) + f" | {sum(p > 0 for p in pdn[:6])}/6 |")
    econ("trades ahead of him (k)", lambda r: hisk[r["li"]], [lambda k: k == 0, lambda k: k == 1, lambda k: 2 <= k <= 3, lambda k: 4 <= k <= 7, lambda k: k >= 8],
         ["k=0", "k=1", "k=2-3", "k=4-7", "k>=8"])
    econ("price paid vs post-dump", lambda r: hispr[r["li"]], [lambda x: x <= 1.02, lambda x: 1.02 < x <= 1.05, lambda x: 1.05 < x <= 1.10, lambda x: 1.10 < x <= 1.20, lambda x: x > 1.20],
         ["<=1.02", "1.02-1.05", "1.05-1.10", "1.10-1.20", ">1.20"])
    econ("hold", lambda r: r["hold"] if r["hold"] is not None else 1e9, [lambda h: h < 1, lambda h: 1 <= h < 2, lambda h: 2 <= h < 4, lambda h: 4 <= h < 8, lambda h: 8 <= h < 15, lambda h: 15 <= h < 60, lambda h: h >= 60],
         ["<1 s", "1-2 s", "2-4 s", "4-8 s", "8-15 s", "15-60 s", ">=60 s"])
    econ("seller type", lambda r: r["d_type"], [lambda t, s=s: t == s for s in ("dev", "bundler", "early", "other")], ["dev", "bundler", "early", "other"])
    econ("token age at the dump", lambda r: r["age"] * 0.212 if r["age"] is not None else 1e9, [lambda a: a < 3, lambda a: 3 <= a < 6, lambda a: 6 <= a < 15, lambda a: 15 <= a < 60, lambda a: a >= 60],
         ["<3 s", "3-6 s", "6-15 s", "15-60 s", ">=60 s"])
    # ---------------- non-dump lots
    P("\n## 4. The non-dump lots (no >= 5 % outside drop within 2 slots before the buy): what preceded them (MEASURED)")
    P("| code | lots | net SOL | mSOL/lot | biggest drop in last 5 slots p50 | that drop 3-5 slots before | k-th buy in trip > 1 (another haqq bot holds) | age < 6 s | price change last 10 slots p50 | outside buy SOL last 3 slots p50 |")
    P("|---|---|---|---|---|---|---|---|---|---|")
    for c in (247, 248):
        v = [r for r in rows if r["code"] == c and ok(r) and not r["dump"]]
        P(f"| {c} | {len(v):,} | {sum(r['net'] for r in v):+.2f} | {1000 * np.mean([r['net'] for r in v]):+.2f} | {np.nanmedian([r['d_drop'] or 0 for r in v]):.3f} | "
          f"{100 * np.mean([(r['d_drop'] or 0) >= 0.05 and (r['d_slots'] or 0) > 2 for r in v]):.0f}% | {100 * np.mean([r['kbuy'] > 1 for r in v]):.0f}% | "
          f"{100 * np.mean([(r['age'] or 1e9) * 0.212 < 6 for r in v]):.0f}% | {np.nanmedian([r['ch10'] if r['ch10'] is not None else np.nan for r in v]):+.3f} | {np.median([r['bo3'] for r in v]):.2f} |")
        sub = collections.Counter()
        for r in v:
            if (r["d_drop"] or 0) >= 0.05: sub["late dump (3-5 slots after a >=5 % drop)"] += 1
            elif (r["d_drop"] or 0) >= 0.02: sub["small dip 2-5 %"] += 1
            elif r["ch10"] is not None and r["ch10"] > 0.10: sub["momentum (+10 % in 10 slots)"] += 1
            else: sub["other"] += 1
        for k, n in sub.most_common():
            w = [r for r in v if ((r["d_drop"] or 0) >= 0.05 and k.startswith("late")) or (0.02 <= (r["d_drop"] or 0) < 0.05 and k.startswith("small"))
                 or ((r["d_drop"] or 0) < 0.02 and r["ch10"] is not None and r["ch10"] > 0.10 and k.startswith("momentum"))
                 or (k == "other" and (r["d_drop"] or 0) < 0.02 and not (r["ch10"] is not None and r["ch10"] > 0.10))]
            P(f"|  | {k} | {n:,} | {sum(r['net'] for r in w):+.2f} | {1000 * np.mean([r['net'] for r in w]):+.2f} | | | | | | |")
    P.save()


if __name__ == "__main__":
    main()
