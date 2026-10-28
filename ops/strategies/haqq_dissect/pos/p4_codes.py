#!/usr/bin/env python3
"""pos step 4 (read-only): haqq = several independent sub-bots in one wallet. Every haqq tx carries a code in its CU price
(cup mod 1000); 99.97% of sold tokens go to an open lot of the SAME code (p1 log), so each code is a bot with its own lots.
Lots here use CODE-MATCHED accounting (exact per bot). MEASURED unless marked.
 1. per code per day: lots, SOL, net, per lot, win, hold, size;
 2. stacking: a lot's P&L by how many OTHER codes already held the token when it bought (causal: his own open lots) and, for
    information only, by how many joined later (outcome);
 3. same-code re-entries on a token, by that code's previous result on the token (causal: previous lot closed before);
 4. k-th buy in the trip with code-matched accounting.
Out: p4.txt"""
import collections, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos")
from plib import *

P = Out(f"{OUT}/p4.txt")
CODES = (248, 247, 244, 226, 234, 231, 251)


def line(nm, v, key="cnet"):
    x = [l[key] for l in v]
    if not x: return
    lo, hi = boot_sum(x); pd = [sum(l[key] for l in v if l["day"] == d) for d in range(6)]
    P(f"| {nm} | {len(v):,} | {sum(x):+.2f} [{lo:+.1f}..{hi:+.1f}] | {1000 * np.mean(x):+.2f} | {100 * np.mean([y > 0 for y in x]):.0f}% | "
      + " ".join(f"{p:+.1f}" for p in pd) + f" | {sum(p > 0 for p in pd)}/6 |")


def main():
    B, LO, T = load()
    ok = lambda t: not t["mayhem"] and not t["gap"]
    LG = [l for l in LO if ok(T[l["trip_ix"]]) and l["code"] is not None]
    P(f"# haqq sub-bots by CU-price code (code-matched lots), {len(LG):,} lots with a code (of {len(LO):,})")
    P("\n## 1. Per code: lots, size, net (code-matched, after pump fees + measured tx costs)")
    P("| code | lots | SOL in | net SOL [90%] | mean mSOL | win | hold p10/p50/p90 s | size p50 | 1st in trip | D0..D5 net | days > 0 |")
    P("|---|---|---|---|---|---|---|---|---|---|---|")
    byc = collections.defaultdict(list)
    for l in LG: byc[l["code"]].append(l)
    for c, v in sorted(byc.items(), key=lambda kv: -len(kv[1])):
        if len(v) < 50: continue
        x = [l["cnet"] for l in v]; lo, hi = boot_sum(x); pd = [sum(l["cnet"] for l in v if l["day"] == d) for d in range(6)]
        hs = [l["chold_s"] for l in v if l["chold_s"] is not None]
        P(f"| {c} | {len(v):,} | {sum(l['cost'] for l in v):.0f} | {sum(x):+.2f} [{lo:+.1f}..{hi:+.1f}] | {1000 * np.mean(x):+.2f} | {100 * np.mean([y > 0 for y in x]):.0f}% | "
          f"{' / '.join(f'{q:.1f}' for q in np.percentile(hs, [10, 50, 90]))} | {np.median([l['cost'] for l in v]):.2f} | {100 * np.mean([l['kbuy'] == 1 for l in v]):.0f}% | "
          + " ".join(f"{p:+.1f}" for p in pd) + f" | {sum(p > 0 for p in pd)}/6 |")
    P(f"\nAll codes: net {sum(l['cnet'] for l in LG):+.2f} SOL (FIFO across codes {sum(l['net'] for l in LG):+.2f}; pro-rata {sum(l['pnet'] for l in LG):+.2f})")
    # ---- stacking: other codes holding at the buy (causal) / joining later (outcome)
    for l in LG: l["_others_at"] = 0; l["_others_later"] = 0; l["_same_before"] = None
    bytrip = collections.defaultdict(list)
    for l in LG: bytrip[l["trip_ix"]].append(l)
    for ti, v in bytrip.items():
        v.sort(key=lambda l: l["cc"])
        for i, l in enumerate(v):
            l["_others_at"] = len({o["code"] for o in v[:i] if o["code"] != l["code"] and (o["cclose_cc"] is None or o["cclose_cc"] > l["cc"])})
            l["_others_later"] = len({o["code"] for o in v[i + 1:] if o["code"] != l["code"]})
    P("\n## 2. Stacking: a bot's lot by how many OTHER codes already held the token when it bought (CAUSAL: his own open lots)")
    P("| code | others holding | lots | net SOL [90%] | mean mSOL | win | D0..D5 | days > 0 |"); P("|---|---|---|---|---|---|---|---|")
    for c in CODES + ("ALL",):
        for k, f in (("0", lambda x: x == 0), ("1", lambda x: x == 1), ("2+", lambda x: x >= 2)):
            v = [l for l in LG if (c == "ALL" or l["code"] == c) and f(l["_others_at"])]
            if len(v) < 30: continue
            x = [l["cnet"] for l in v]; lo, hi = boot_sum(x); pd = [sum(l["cnet"] for l in v if l["day"] == d) for d in range(6)]
            P(f"| {c} | {k} | {len(v):,} | {sum(x):+.2f} [{lo:+.1f}..{hi:+.1f}] | {1000 * np.mean(x):+.2f} | {100 * np.mean([y > 0 for y in x]):.0f}% | "
              + " ".join(f"{p:+.1f}" for p in pd) + f" | {sum(p > 0 for p in pd)}/6 |")
    P("\nFor information (OUTCOME-conditioned, not tradable): lots by how many other codes joined the trip AFTER them")
    P("| others joined later | lots | net SOL | mean mSOL | win |"); P("|---|---|---|---|---|")
    for k, f in (("0", lambda x: x == 0), ("1", lambda x: x == 1), ("2+", lambda x: x >= 2)):
        v = [l for l in LG if f(l["_others_later"])]
        P(f"| {k} | {len(v):,} | {sum(l['cnet'] for l in v):+.2f} | {1000 * np.mean([l['cnet'] for l in v]):+.2f} | {100 * np.mean([l['cnet'] > 0 for l in v]):.0f}% |")
    # ---- same-code re-entries on a token
    P("\n## 3. Same code buying the same token again (any trip), by that code's PREVIOUS lot on the token (CAUSAL: previous lot closed before)")
    bym = collections.defaultdict(list)
    for l in sorted(LG, key=lambda l: l["cc"]): bym[(l["mint"], l["code"])].append(l)
    rows = collections.defaultdict(list)
    for (m, c), v in bym.items():
        for i, l in enumerate(v):
            if i == 0: rows["first time this code buys the token"].append(l); continue
            pv = v[i - 1]
            if pv["cclose_cc"] is None or pv["cclose_cc"] > l["cc"]: rows["previous same-code lot still open (stack)"].append(l); continue
            r = pv["cgross"] / pv["cost"]
            k = ("prev lot < -5%" if r < -0.05 else "prev lot -5..+2%" if r < 0.02 else "prev lot +2..+15%" if r < 0.15 else "prev lot >= +15%")
            rows[k].append(l)
    P("| case | lots | net SOL [90%] | mean mSOL | win | D0..D5 | days > 0 |"); P("|---|---|---|---|---|---|---|")
    for k in ("first time this code buys the token", "previous same-code lot still open (stack)", "prev lot < -5%", "prev lot -5..+2%", "prev lot +2..+15%", "prev lot >= +15%"):
        line(k, rows.get(k, []))
    P("\nShare of each code's lots that are re-entries on a token it traded before:")
    for c in CODES:
        v = [l for (m, cc), vv in bym.items() if cc == c for l in vv]
        if v: P(f"- {c}: {len(v):,} lots, re-entries {100 * (1 - len([1 for (m, cc), vv in bym.items() if cc == c]) / len(v)):.0f}%")
    # ---- k-th buy, code-matched
    P("\n## 4. k-th buy in the trip, code-matched accounting (compare FIFO in p2 section 4)")
    P("| k | lots | net SOL [90%] | mean mSOL | win | D0..D5 | days > 0 |"); P("|---|---|---|---|---|---|---|")
    for kb in (1, 2, 3, 4, 5, 6):
        line(str(kb) if kb < 6 else "6+", [l for l in LG if not l["probe"] and (l["kbuy"] == kb if kb < 6 else l["kbuy"] >= 6)])
    P("\n## 5. Trip classes with code-matched lots: is the multi-buy profit in the FIRST lot or the added lots? (outcome-conditioned)")
    P("| trip buys | trips | first lot net | added lots net | first lot mean mSOL | added lot mean mSOL | distinct codes p50 |"); P("|---|---|---|---|---|---|---|")
    for lo_, hi_ in ((1, 1), (2, 2), (3, 4), (5, 999)):
        tt = [ti for ti, v in bytrip.items() if lo_ <= len(v) <= hi_ and not T[ti]["probe"]]
        f = [bytrip[ti][0]["cnet"] for ti in tt]; a = [l["cnet"] for ti in tt for l in bytrip[ti][1:]]
        P(f"| {lo_}-{hi_} | {len(tt):,} | {sum(f):+.2f} | {sum(a):+.2f} | {1000 * np.mean(f):+.2f} | {1000 * np.mean(a) if a else 0:+.2f} | "
          f"{np.median([len({l['code'] for l in bytrip[ti]}) for ti in tt]):.0f} |")
    P.save()


if __name__ == "__main__":
    main()
