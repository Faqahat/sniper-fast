#!/usr/bin/env python3
"""pos step 2 (read-only): haqq's trips per day by (#buys, #sells) class; lot P&L by k-th buy (FIFO and pro-rata); k-th trip on a
token. All MEASURED from the tape (p1.pkl); tx costs measured per tx where the raw recording has it (10-25 19:20 ->), else
0.396 mSOL/tx (INFERRED from the measured mean). Mayhem, probe (<= 0.05 SOL) and coverage-gap trips excluded (counted).
Out: p2.txt"""
import collections, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos")
from plib import *

P = Out(f"{OUT}/p2.txt")


def cls(t):
    if t["nb"] == 1: return "1/1" if t["ns"] <= 1 else "1/n"
    if t["nb"] == 2: return "2/x"
    if t["nb"] <= 4: return "3-4"
    return "5+"


def main():
    B, LO, T = load()
    ok = lambda t: not t["mayhem"] and not t["probe"] and not t["gap"]
    P("# haqq trips on the whole tape (10-22 03:07 -> 10-28 01:12 PKT); days end 23:15 PKT")
    c = collections.Counter(("mayhem" if t["mayhem"] else "probe" if t["probe"] else "gap" if t["gap"] else "ok") for t in T)
    P(f"trips {len(T):,}: {dict(c)}; open at tape end (marked) {sum(1 for t in T if t.get('open_end'))}; measured-cost share of ok trips "
      f"{100 * np.mean([t['meas_cost'] for t in T if ok(t)]):.0f}%")
    mh = [t for t in T if t["mayhem"]]
    P(f"mayhem trips: {len(mh)}, net {sum(t['net'] for t in mh):+.2f} SOL (excluded below)")
    G = [t for t in T if ok(t)]
    # --- per day x class
    P("\n## 1. Trips per day by (#buys / #sells) class (MEASURED; net = after pump fees and tx costs)")
    P("| day | class | trips | SOL in | net SOL [90% boot] | net per SOL | win | hold p50 s | share of day net |")
    P("|---|---|---|---|---|---|---|---|---|")
    J = {}
    for d in DAYS:
        g = [t for t in G if t["day"] == d]
        if not g: continue
        dn = sum(t["net"] for t in g)
        for k in ("1/1", "1/n", "2/x", "3-4", "5+", "ALL"):
            v = g if k == "ALL" else [t for t in g if cls(t) == k]
            if not v: continue
            n = sum(t["net"] for t in v); sol = sum(t["cost"] for t in v); lo, hi = boot_sum([t["net"] for t in v])
            hs = [t["hold_s"] for t in v if t["hold_s"] is not None]
            P(f"| {day_name(d) if k == '1/1' else ''} | {k} | {len(v):,} | {sol:.0f} | {n:+.2f} [{lo:+.1f}..{hi:+.1f}] | {100 * n / sol:+.2f}% | "
              f"{100 * np.mean([t['net'] > 0 for t in v]):.0f}% | {np.median(hs) if hs else float('nan'):.1f} | {100 * n / dn if k != 'ALL' else 100:.0f}% |")
            J[(d, k)] = n
    P("\nShare of each day's net from multi-buy trips (2+ buys) and from 3+ buy trips:")
    for d in DAYS:
        g = [t for t in G if t["day"] == d]
        if not g: continue
        dn = sum(t["net"] for t in g)
        m2 = sum(t["net"] for t in g if t["nb"] >= 2); m3 = sum(t["net"] for t in g if t["nb"] >= 3)
        P(f"- {day_name(d)}: day net {dn:+.2f}; 2+ buys {m2:+.2f} ({100 * m2 / dn:.0f}%); 3+ buys {m3:+.2f} ({100 * m3 / dn:.0f}%); "
          f"1-buy {dn - m2:+.2f}; trips {len(g):,}, 2+ buy share of trips {100 * np.mean([t['nb'] >= 2 for t in g]):.0f}%")
    # --- by buys per trip, all days (main-session table, multi-day)
    P("\n## 2. By buys per trip, per day (net SOL; trips in brackets)")
    P("| day | 1 buy | 2 | 3-4 | 5+ |"); P("|---|---|---|---|---|")
    for d in DAYS:
        g = [t for t in G if t["day"] == d]
        if not g: continue
        row = []
        for lo_, hi_ in ((1, 1), (2, 2), (3, 4), (5, 999)):
            v = [t for t in g if lo_ <= t["nb"] <= hi_]
            row.append(f"{sum(t['net'] for t in v):+.2f} ({len(v):,})")
        P(f"| {day_name(d)} | " + " | ".join(row) + " |")
    # --- GMGN impression check: 1/1 small losses?
    P("\n## 3. The GMGN impression: are 1/1 trips small losers and multi-buy trips big winners? (all days, ok trips)")
    P("| class | trips | median return | p10 / p90 return | mean net mSOL | win | share of trips with ret < -10% |")
    P("|---|---|---|---|---|---|---|")
    for k in ("1/1", "1/n", "2/x", "3-4", "5+"):
        v = [t for t in G if cls(t) == k]
        r = np.array([t["net"] / t["cost"] for t in v])
        P(f"| {k} | {len(v):,} | {100 * np.median(r):+.1f}% | {100 * np.percentile(r, 10):+.1f}% / {100 * np.percentile(r, 90):+.1f}% | "
          f"{1000 * np.mean([t['net'] for t in v]):+.2f} | {100 * np.mean(r > 0):.0f}% | {100 * np.mean(r < -0.10):.0f}% |")
    # --- lots by k-th buy (FIFO and pro-rata)
    P("\n## 4. Lots by k-th buy in the trip, FIFO and pro-rata (average-cost) accounting, per day (net mSOL per lot; lots)")
    LG = [l for l in LO if not l["probe"] and ok(T[l["trip_ix"]])]
    P("| k | lots (all days) | FIFO net SOL [90%] | pro-rata net SOL [90%] | FIFO per lot mSOL | per-day FIFO net SOL D0..D6 | days > 0 |")
    P("|---|---|---|---|---|---|---|")
    for kb in (1, 2, 3, 4, 5, 6):
        v = [l for l in LG if (l["kbuy"] == kb if kb < 6 else l["kbuy"] >= 6)]
        f = [l["net"] for l in v]; p = [l["pnet"] for l in v]
        pd = [sum(l["net"] for l in v if l["day"] == d) for d in DAYS]
        P(f"| {kb if kb < 6 else '6+'} | {len(v):,} | {sum(f):+.2f} [{boot_sum(f)[0]:+.1f}..{boot_sum(f)[1]:+.1f}] | {sum(p):+.2f} [{boot_sum(p)[0]:+.1f}..{boot_sum(p)[1]:+.1f}] | "
          f"{1000 * np.mean(f):+.2f} | " + " ".join(f"{x:+.1f}" for x in pd) + f" | {sum(x > 0 for x in pd[1:6])}/5 |")
    # first lot of long trips vs short trips
    P("\nFIRST lot P&L by the trip's eventual number of buys (FIFO; outcome-conditioned, NOT causal):")
    for lo_, hi_ in ((1, 1), (2, 2), (3, 4), (5, 999)):
        v = [l for l in LG if l["kbuy"] == 1 and lo_ <= T[l["trip_ix"]]["nb"] <= hi_]
        P(f"- trips with {lo_}-{hi_} buys: first lots {len(v):,}, net {sum(l['net'] for l in v):+.2f}, mean {1000 * np.mean([l['net'] for l in v]):+.2f} mSOL, "
          f"hold p50 {np.median([l['hold_s'] for l in v if l['hold_s'] is not None]):.1f} s")
    # --- k-th trip on the token
    P("\n## 5. k-th trip on a token (net SOL per day; trips)")
    P("| day | 1st | 2nd | 3rd | 4th-5th | 6th+ |"); P("|---|---|---|---|---|---|")
    for d in DAYS:
        g = [t for t in G if t["day"] == d]
        if not g: continue
        row = []
        for lo_, hi_ in ((1, 1), (2, 2), (3, 3), (4, 5), (6, 9999)):
            v = [t for t in g if lo_ <= t["k"] <= hi_]
            row.append(f"{sum(t['net'] for t in v):+.2f} ({len(v):,})")
        P(f"| {day_name(d)} | " + " | ".join(row) + " |")
    # tokens by number of trips
    P("\nTokens by the number of trips he makes on them (all days; outcome-conditioned):")
    bym = collections.defaultdict(list)
    for t in G: bym[t["mint"]].append(t)
    for lo_, hi_ in ((1, 1), (2, 2), (3, 5), (6, 9999)):
        v = [ts for ts in bym.values() if lo_ <= len(ts) <= hi_]
        P(f"- {lo_}-{hi_} trips: tokens {len(v):,}, net {sum(t['net'] for ts in v for t in ts):+.2f}, first-trip net {sum(ts[0]['net'] for ts in v):+.2f}")
    P.save()


if __name__ == "__main__":
    main()
