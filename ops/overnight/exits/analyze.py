#!/usr/bin/env python3
# READ-ONLY, offline. Measured exit behaviour of the two AKbot wallets from their own round trips (all SOL-quoted pump tokens):
# sell counts / timing / sizes, the "lightning" first sell, per-piece PnL attribution by price multiple, and which pieces carry
# the profit.  usage: python3 -I analyze.py > analyze.txt
import sys, os, json, collections, statistics, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

def pieces(r):
    """PnL of every sell piece: net SOL received in the sell tx minus the cost basis of the tokens it sold
    (cost basis = all-in buy cost incl. tip, priority, rent, pump fee and the 1% AKbot buy fee, pro rata to tokens)."""
    tok_bought = sum(l["tok"] for l in r["legs"] if l["side"] == "buy")
    out = []
    for l in r["legs"]:
        if l["side"] != "sell": continue
        c = r["cost"] * l["tok"] / tok_bought if tok_bought else 0
        out.append(dict(l, piece_pnl=l["net"] - c, piece_cost=c))
    return out

def q(v, ps=(0.1, 0.25, 0.5, 0.75, 0.9)):
    v = sorted(v)
    return [round(v[min(len(v) - 1, int(p * len(v)))], 3) for p in ps] if v else []

if __name__ == "__main__":
    for w in WALLETS:
        R = [r for r in json.load(open(f"{EXITS}/roundtrips_{w}.json"))["tokens"] if r["n_sells"]]
        L = [r for r in R if r["period"] == "ledger"]
        print(f"\n=================== {w}: {len(R)} round trips ({len(L)} in the 10-17..10-22 ledger, {len(R) - len(L)} after it)")
        for name, S in (("ledger 10-17..10-22", L), ("all incl. recent", R)):
            print(f"  [{name}] PnL {sum(r['pnl'] for r in S):+.2f} SOL | win {sum(r['pnl'] > 0 for r in S) / len(S):.0%} | buy SOL {sum(r['buy_sol'] for r in S):.1f} | "
                  f"curve gross {sum(r['gross_curve'] for r in S):+.2f} | AKbot buy fee {sum(r['ak_buy'] for r in S):.2f}")
        S = L   # detailed tables: the 10-17..10-22 ledger period (ground-truth window)
        # sells per token & hold
        ns = collections.Counter("1" if r["n_sells"] == 1 else "2" if r["n_sells"] == 2 else "3-5" if r["n_sells"] <= 5 else "6+" for r in S)
        print("  sells/token:", {k: (ns[k], round(sum(r['pnl'] for r in S if ('1' if r['n_sells'] == 1 else '2' if r['n_sells'] == 2 else '3-5' if r['n_sells'] <= 5 else '6+') == k), 2)) for k in ("1", "2", "3-5", "6+")})
        print("  hold slots quantiles (10/25/50/75/90%):", q([r["hold_slots"] for r in S]), "| hold s:", q([r["hold_s"] for r in S]))
        # first sell
        F = [next(l for l in r["legs"] if l["side"] == "sell") for r in S]
        print("  FIRST sell dslot:", sorted(collections.Counter(min(l['dslot'], 20) for l in F).items()))
        fast = [l for l in F if l["dslot"] <= 8]
        print(f"  first sell <= 8 slots after buy: {len(fast)}/{len(F)} ({len(fast) / len(F):.0%}); its fraction quantiles {q([l['frac'] for l in fast])}; "
              f"its price multiple quantiles {q([l['mult_pre'] for l in fast])}; share of first sells at a loss (mult<1) {sum(l['mult_pre'] < 1 for l in fast) / max(1, len(fast)):.0%}")
        # piece attribution
        P = [(r, p) for r in S for p in pieces(r)]
        band = lambda x: "<0.7" if x < 0.7 else "0.7-0.85" if x < 0.85 else "0.85-1" if x < 1 else "1-1.15" if x < 1.15 else "1.15-1.3" if x < 1.3 else "1.3-1.5" if x < 1.5 else "1.5-2" if x < 2 else "2-3" if x < 3 else "3+"
        g = collections.defaultdict(lambda: [0, 0.0, 0.0, 0.0])
        for r, p in P:
            k = band(p["mult_exec"]); g[k][0] += 1; g[k][1] += p["piece_pnl"]; g[k][2] += p["tok"] / sum(l["tok"] for l in r["legs"] if l["side"] == "buy"); g[k][3] += p["piece_cost"]
        print("  per sell piece by exec price multiple vs entry: band: n pieces | PnL SOL | position-equivalents sold | cost basis SOL")
        for k in ("<0.7", "0.7-0.85", "0.85-1", "1-1.15", "1.15-1.3", "1.3-1.5", "1.5-2", "2-3", "3+"):
            if k in g: print(f"     {k:9} {g[k][0]:5d} | {g[k][1]:+7.2f} | {g[k][2]:6.1f} | {g[k][3]:7.1f}")
        # piece type
        def ptype(r, p, i, n):
            if i == 0 and p["dslot"] <= 8: return "1 lightning (1st sell <=8 slots)"
            if i == n - 1: return "3 final clear"
            return "2 middle partial"
        g2 = collections.defaultdict(lambda: [0, 0.0, 0.0])
        for r in S:
            ps = pieces(r)
            for i, p in enumerate(ps):
                k = ptype(r, p, i, len(ps)); g2[k][0] += 1; g2[k][1] += p["piece_pnl"]; g2[k][2] += p["tok"] / sum(l["tok"] for l in r["legs"] if l["side"] == "buy")
        print("  per piece type: n | PnL | position-equivalents:", {k: (v[0], round(v[1], 2), round(v[2], 1)) for k, v in sorted(g2.items())})
        # winners: how much profit from pieces >= 2x / 1.5x
        Wn = [r for r in S if r["pnl"] > 0]; Ls = [r for r in S if r["pnl"] <= 0]
        wp = sum(r["pnl"] for r in Wn)
        def share(th): return sum(p["piece_pnl"] for r in Wn for p in pieces(r) if p["mult_exec"] >= th)
        print(f"  winners {len(Wn)}: PnL {wp:+.2f}; from pieces sold >= 2x {share(2.0):+.2f}, >= 1.5x {share(1.5):+.2f}, >= 1.3x {share(1.3):+.2f}; losers {len(Ls)}: PnL {sum(r['pnl'] for r in Ls):+.2f}")
        # size tiers
        tier = lambda s: "<1.5" if s < 1.5 else "1.5-2.4" if s < 2.4 else "2.4-4" if s < 4 else "4+"
        g3 = collections.defaultdict(list)
        for r in S: g3[tier(r["buy_sol"])].append(r)
        print("  by buy size:", {k: (len(v), round(sum(r['pnl'] for r in v), 2), f"win {sum(r['pnl'] > 0 for r in v) / len(v):.0%}") for k, v in sorted(g3.items())})
        # max multiple ever sold at and final multiple
        print("  max sold multiple quantiles:", q([max(l['mult_pre'] for l in r['legs'] if l['side'] == 'sell') for r in S]),
              "| final-clear multiple quantiles:", q([[l for l in r['legs'] if l['side'] == 'sell'][-1]['mult_pre'] for r in S]))
