#!/usr/bin/env python3
"""pos step 3 (read-only): the ladder. Every ADD (k-th buy, k >= 2, inside a trip) and every RE-ENTRY (first buy of trip k >= 2 on a
token) of haqq, with its own P&L (FIFO + pro-rata) and the causal context at the add (MEASURED from the tape, rows before the add).
Also the B/S sequence patterns inside trips and the token-level (GMGN-like) view.
Out: p3.txt"""
import collections, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos")
from plib import *

P = Out(f"{OUT}/p3.txt")


def tab(title, rows, keyf, buckets, val="net"):
    P(f"\n### {title}")
    P("| bucket | n | code-matched net SOL [90%] | mean mSOL | FIFO net SOL | win | days > 0 (D0..D5) |"); P("|---|---|---|---|---|---|---|")
    for nm, f in buckets:
        v = [r for r in rows if f(keyf(r))]
        if not v: continue
        x = [r["lot"]["cnet"] for r in v]; lo, hi = boot_sum(x)
        pd = [sum(r["lot"]["cnet"] for r in v if r["lot"]["day"] == d) for d in range(6)]
        P(f"| {nm} | {len(v):,} | {sum(x):+.2f} [{lo:+.1f}..{hi:+.1f}] | {1000 * np.mean(x):+.2f} | {sum(r["lot"]["net"] for r in v):+.2f} | "
          f"{100 * np.mean([y > 0 for y in x]):.0f}% | {sum(p > 0 for p in pd)}/6 |")


def add_class(b, t):
    """causal class of an add (inside a trip)"""
    if b["dt_prev_slots"] is not None and b["dt_prev_slots"] <= 1 and not b["sold_since_prev"] and not b["d_after_prev"]:
        return "A0 double (<=1 slot after prev buy, same dump, no sell between)"
    newdump = b["d_after_prev"] and b["d_drop"] >= 0.05 and b["d_slots"] is not None and b["d_slots"] <= 2
    u = b["unreal"] if b["unreal"] is not None else 0.0
    if newdump and u < 0: return "A1 new dump, position under water (average down)"
    if newdump: return "A2 new dump, position in profit"
    if b["px_vs_prev"] is not None and b["px_vs_prev"] > 0.03 and b["bo3"] > b["so3"]: return "A3 momentum (price > prev buy +3%, buy flow)"
    if u < 0: return "A4 no new dump, under water"
    return "A5 no new dump, in profit/flat"


def main():
    B, LO, T = load()
    ok = lambda t: not t["mayhem"] and not t["probe"] and not t["gap"]
    rows = []
    for l in LO:
        t = T[l["trip_ix"]]
        if l["probe"] or not ok(t): continue
        rows.append(dict(lot=l, b=B[l["b"]], t=t))
    adds = [r for r in rows if r["b"]["kbuy"] >= 2]
    firsts = [r for r in rows if r["b"]["kbuy"] == 1]
    P(f"# haqq ladder (all days, ok trips): lots {len(rows):,}, first buys {len(firsts):,}, adds {len(adds):,}")
    P(f"FIFO net: first lots {sum(r['lot']['net'] for r in firsts):+.2f}, adds {sum(r['lot']['net'] for r in adds):+.2f} SOL")
    # ---- timing of adds
    tab("Adds by time since the previous buy (slots)", adds, lambda r: r["b"]["dt_prev_slots"],
        [("0 (same slot)", lambda x: x == 0), ("1", lambda x: x == 1), ("2-3", lambda x: 2 <= x <= 3), ("4-10", lambda x: 4 <= x <= 10),
         ("11-30", lambda x: 11 <= x <= 30), ("31-100", lambda x: 31 <= x <= 100), ("> 100", lambda x: x > 100)])
    tab("Adds by price vs his previous buy (pre-trade price)", adds, lambda r: r["b"]["px_vs_prev"],
        [("< -20%", lambda x: x < -0.2), ("-20..-10%", lambda x: -0.2 <= x < -0.1), ("-10..-3%", lambda x: -0.1 <= x < -0.03),
         ("-3..+3%", lambda x: -0.03 <= x < 0.03), ("+3..+10%", lambda x: 0.03 <= x < 0.1), ("+10..+25%", lambda x: 0.1 <= x < 0.25), ("> +25%", lambda x: x >= 0.25)])
    tab("Adds by the open position's unrealized return at the add (exact curve, net of fee)", adds, lambda r: r["b"]["unreal"],
        [("< -20%", lambda x: x is not None and x < -0.2), ("-20..-10%", lambda x: x is not None and -0.2 <= x < -0.1),
         ("-10..-3%", lambda x: x is not None and -0.1 <= x < -0.03), ("-3..+3%", lambda x: x is not None and -0.03 <= x < 0.03),
         ("+3..+10%", lambda x: x is not None and 0.03 <= x < 0.1), ("> +10%", lambda x: x is not None and x >= 0.1)])
    tab("Adds: did he sell part of the position between the previous buy and the add?", adds, lambda r: r["b"]["sold_since_prev"],
        [("sold some first", lambda x: x), ("no sell between", lambda x: not x)])
    tab("Adds: a NEW outside dump (>=5% single sell) within 2 slots before the add, after his previous buy?", adds,
        lambda r: (r["b"]["d_after_prev"] and r["b"]["d_drop"] >= 0.05 and (r["b"]["d_slots"] or 99) <= 2),
        [("new dump", lambda x: x), ("no new dump", lambda x: not x)])
    nd = [r for r in adds if r["b"]["d_after_prev"] and r["b"]["d_drop"] >= 0.05 and (r["b"]["d_slots"] or 99) <= 2]
    tab("Adds on a new dump: dump size (single-sell drop)", nd, lambda r: r["b"]["d_drop"],
        [("5-8%", lambda x: x < 0.08), ("8-12%", lambda x: 0.08 <= x < 0.12), ("12-20%", lambda x: 0.12 <= x < 0.2), ("20-35%", lambda x: 0.2 <= x < 0.35), (">= 35%", lambda x: x >= 0.35)])
    tab("Adds on a new dump: dump SOL", nd, lambda r: r["b"]["d_sol"],
        [("< 0.5", lambda x: x < 0.5), ("0.5-1", lambda x: 0.5 <= x < 1), ("1-2", lambda x: 1 <= x < 2), ("2-4", lambda x: 2 <= x < 4), (">= 4", lambda x: x >= 4)])
    tab("Adds by distinct outside wallets that traded between his previous buy and the add", adds, lambda r: r["b"]["nw_since_prev"],
        [("0", lambda x: x == 0), ("1-2", lambda x: 1 <= x <= 2), ("3-5", lambda x: 3 <= x <= 5), ("6-10", lambda x: 6 <= x <= 10), ("11-25", lambda x: 11 <= x <= 25), ("> 25", lambda x: x > 25)])
    tab("Adds by price vs the 10-slot high (drawdown)", adds, lambda r: r["b"]["dd10"],
        [("< 3%", lambda x: x < 0.03), ("3-10%", lambda x: 0.03 <= x < 0.1), ("10-20%", lambda x: 0.1 <= x < 0.2), ("20-35%", lambda x: 0.2 <= x < 0.35), (">= 35%", lambda x: x >= 0.35)])
    tab("Adds by outside net flow in the last 3 slots (buy SOL - sell SOL)", adds, lambda r: r["b"]["bo3"] - r["b"]["so3"],
        [("< -3", lambda x: x < -3), ("-3..-1", lambda x: -3 <= x < -1), ("-1..0", lambda x: -1 <= x < 0), ("0..1", lambda x: 0 <= x < 1), ("1..3", lambda x: 1 <= x < 3), (">= 3", lambda x: x >= 3)])
    tab("Adds by the k-th buy", adds, lambda r: r["b"]["kbuy"], [("2", lambda x: x == 2), ("3", lambda x: x == 3), ("4", lambda x: x == 4), ("5-6", lambda x: 5 <= x <= 6), ("7+", lambda x: x >= 7)])
    tab("Adds by size relative to the first buy of the trip", adds, lambda r: r["b"]["size"] / max(B[LO[r["t"]["lots"][0]]["b"]]["size"], 1e-9),
        [("< 0.8x", lambda x: x < 0.8), ("0.8-1.2x", lambda x: 0.8 <= x < 1.2), ("1.2-2x", lambda x: 1.2 <= x < 2), (">= 2x", lambda x: x >= 2)])
    # ---- classes
    P("\n## Add classes (causal: every input is known before the add lands)")
    cl = collections.defaultdict(list)
    for r in adds: cl[add_class(r["b"], r["t"])].append(r)
    tab("Adds by class", adds, lambda r: add_class(r["b"], r["t"]), [(k, (lambda kk: (lambda x: x == kk))(k)) for k in sorted(cl)])
    for k in sorted(cl):
        v = cl[k]
        P(f"- {k}: dt prev p50 {np.median([r['b']['dt_prev_slots'] for r in v]):.0f} slots, unreal p50 {100 * np.median([r['b']['unreal'] or 0 for r in v]):+.1f}%, "
          f"hold p50 {np.median([r['lot']['hold_s'] for r in v if r['lot']['hold_s'] is not None]):.1f} s, size p50 {np.median([r['b']['size'] for r in v]):.2f}")
    # ---- re-entries (trip k >= 2): by previous trip result (causal: previous trip closed before)
    re = [r for r in firsts if r["t"]["k"] >= 2]
    P(f"\n## Re-entries (first buy of trip k >= 2 on the token): {len(re):,} lots; FIFO net {sum(r['lot']['net'] for r in re):+.2f}; whole trips net {sum(r['t']['net'] for r in re):+.2f}")
    P("| previous trip result | re-entry trips | trip net SOL [90%] | mean mSOL | win | first-lot net |"); P("|---|---|---|---|---|---|")
    for nm, f in (("prev trip < -10%", lambda x: x < -0.1), ("-10..-2%", lambda x: -0.1 <= x < -0.02), ("-2..+2%", lambda x: -0.02 <= x < 0.02),
                  ("+2..+10%", lambda x: 0.02 <= x < 0.1), ("+10..+25%", lambda x: 0.1 <= x < 0.25), (">= +25%", lambda x: x >= 0.25)):
        v = []
        for r in re:
            pt = T[r["lot"]["trip_ix"] - 1]
            if pt["mint"] != r["t"]["mint"] or pt["cost"] <= 0: continue
            if f(pt["gross"] / pt["cost"]): v.append(r)
        if not v: continue
        x = [r["t"]["net"] for r in v]; lo, hi = boot_sum(x)
        P(f"| {nm} | {len(v):,} | {sum(x):+.2f} [{lo:+.1f}..{hi:+.1f}] | {1000 * np.mean(x):+.2f} | {100 * np.mean([y > 0 for y in x]):.0f}% | {sum(r['lot']['net'] for r in v):+.2f} |")
    P("\nRe-entry by gap since the previous trip closed:")
    for nm, f in (("< 1 s", lambda x: x < 1), ("1-5 s", lambda x: 1 <= x < 5), ("5-30 s", lambda x: 5 <= x < 30), ("30 s-5 min", lambda x: 30 <= x < 300), (">= 5 min", lambda x: x >= 300)):
        v = [r for r in re if r["t"]["prev_close_cc"] and f((r["t"]["cc0"] - r["t"]["prev_close_cc"]) / 1000)]
        if v:
            x = [r["t"]["net"] for r in v]
            P(f"- {nm}: {len(v):,} trips, net {sum(x):+.2f}, mean {1000 * np.mean(x):+.2f} mSOL, win {100 * np.mean([y > 0 for y in x]):.0f}%")
    # ---- B/S sequence patterns inside trips
    P("\n## Sequence patterns inside trips (B = his buy, S = his sell, consecutive same letters merged as counts)")
    seq = collections.defaultdict(list)
    ev = collections.defaultdict(list)
    for i, l in enumerate(LO): ev[l["trip_ix"]].append((l["cc"], "B"))
    import pickle
    Z = pickle.load(open(f"{OUT}/p1.pkl", "rb"))
    for s in Z["sells"]: ev[s["trip_ix"]].append((s["cc"], "S"))
    for ti, t in enumerate(T):
        if not ok(t) or t["nb"] < 2: continue
        e = "".join(x for _, x in sorted(ev[ti]))
        # compress
        c = []
        for ch in e:
            if c and c[-1][0] == ch: c[-1][1] += 1
            else: c.append([ch, 1])
        pat = "".join(f"{a}{n if n > 1 else ''}" for a, n in c)
        if len(pat) > 12: pat = pat[:12] + "..."
        seq[pat].append(t)
    P("| pattern | trips | net SOL | mean mSOL | win |"); P("|---|---|---|---|---|")
    for pat, v in sorted(seq.items(), key=lambda kv: -len(kv[1]))[:20]:
        P(f"| {pat} | {len(v):,} | {sum(t['net'] for t in v):+.2f} | {1000 * np.mean([t['net'] for t in v]):+.2f} | {100 * np.mean([t['net'] > 0 for t in v]):.0f}% |")
    # ---- token-level (GMGN) view: tokens per day by total buys
    P("\n## Token-level view (GMGN groups all trips of a token): tokens by his total buys on the token, all days")
    tk = collections.defaultdict(list)
    for t in T:
        if ok(t): tk[t["mint"]].append(t)
    P("| buys on the token | tokens | net SOL | mean mSOL | win | median trips | first-trip net |"); P("|---|---|---|---|---|---|---|")
    for nm, f in (("1", lambda x: x == 1), ("2", lambda x: x == 2), ("3-4", lambda x: 3 <= x <= 4), ("5-8", lambda x: 5 <= x <= 8), ("9+", lambda x: x >= 9)):
        v = [ts for ts in tk.values() if f(sum(t["nb"] for t in ts))]
        x = [sum(t["net"] for t in ts) for ts in v]
        P(f"| {nm} | {len(v):,} | {sum(x):+.2f} | {1000 * np.mean(x):+.2f} | {100 * np.mean([y > 0 for y in x]):.0f}% | {np.median([len(ts) for ts in v]):.0f} | {sum(ts[0]['net'] for ts in v):+.2f} |")
    P.save()


if __name__ == "__main__":
    main()
