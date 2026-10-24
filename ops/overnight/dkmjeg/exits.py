#!/usr/bin/env python3
# READ-ONLY, offline: dKMjeG's exits from its own ledger (exact TradeEvents): number of sells, timing after the buy
# (slots), share of the position per sell, price multiple vs its own average buy price, PnL by exit shape / size tier.
import json, collections, statistics as S
L = json.load(open("/home/moiz/sniper/ops/overnight/dkmjeg/ledger.json")); T = L["tokens"]
SLOT = 0.212
q = lambda xs, p: round(sorted(xs)[int(p * (len(xs) - 1))], 3) if xs else None
toks = [(m, x) for m, x in T.items() if x["buys"] and x["quote"] == "SOL" and x["sells_list"] and x.get("buy_tok")]
print(f"SOL-quoted tokens with a buy and >= 1 sell: {len(toks)}")
def tier(x):
    s = x["size"] * 1.0125
    for t in (1.8, 2.1, 3.6, 4.2, 5.0, 6.0, 7.0, 8.0, 12.0):
        if abs(s - t) < 0.12: return t
    return "other"
rows = []
for m, x in toks:
    sl = sorted(x["sells_list"], key=lambda s: s["slot"])
    tot = x["buy_tok"]; out = []
    for s in sl:
        out.append(dict(ds=s["slot"] - x["s0"], frac=s["tok"] / tot, x=(s["px"] / x["buy_px"]) if s["px"] and x["buy_px"] else None, sol=s["sol"]))
    rows.append(dict(m=m, tier=tier(x), pnl=x["pnl"], n=len(sl), sells=out, hold=out[-1]["ds"], d=x["d"], size=x["size"] * 1.0125, sold=sum(o["frac"] for o in out)))
ns = collections.Counter(r["n"] for r in rows)
print("sells per token:", sorted(ns.items()))
print("hold (slots, buy -> last sell): p25/med/p75/p90", q([r["hold"] for r in rows], .25), q([r["hold"] for r in rows], .5), q([r["hold"] for r in rows], .75), q([r["hold"] for r in rows], .9),
      "| in seconds med", round(q([r["hold"] for r in rows], .5) * SLOT, 1))
for k in range(5):
    sk = [r["sells"][k] for r in rows if len(r["sells"]) > k]
    print(f"sell #{k + 1}: n {len(sk)} | slots after buy p25/med/p75 {q([s['ds'] for s in sk], .25)}/{q([s['ds'] for s in sk], .5)}/{q([s['ds'] for s in sk], .75)} | share of position med {q([s['frac'] for s in sk], .5)} | price x entry p25/med/p75 {q([s['x'] for s in sk if s['x']], .25)}/{q([s['x'] for s in sk if s['x']], .5)}/{q([s['x'] for s in sk if s['x']], .75)}")
def cls(f):
    return "100%" if f > 0.99 else "50%" if 0.45 <= f <= 0.55 else "30%" if 0.27 <= f <= 0.33 else "15%" if 0.13 <= f <= 0.17 else "other"
g = collections.defaultdict(list)
for r in rows: g[cls(r["sells"][0]["frac"])].append(r)
print("\nfirst sell share -> tokens, PnL, median first-sell slot and multiple:")
for k, v in sorted(g.items(), key=lambda kv: -len(kv[1])):
    print(f"   {k:6} {len(v):4} tokens {sum(r['pnl'] for r in v):+8.2f} SOL (median {S.median(r['pnl'] for r in v):+.3f}) | first sell slot med {q([r['sells'][0]['ds'] for r in v], .5)} x med {q([r['sells'][0]['x'] for r in v if r['sells'][0]['x']], .5)} | sells med {S.median(r['n'] for r in v)}")
print("\nby number of sells:")
for lab, f in (("1", lambda n: n == 1), ("2", lambda n: n == 2), ("3", lambda n: n == 3), ("4-5", lambda n: 4 <= n <= 5), ("6+", lambda n: n >= 6)):
    v = [r for r in rows if f(r["n"])]
    if v: print(f"   {lab:4} {len(v):4} tokens {sum(r['pnl'] for r in v):+8.2f} SOL, win {sum(r['pnl'] > 0 for r in v) / len(v):.0%}, median {S.median(r['pnl'] for r in v):+.3f}")
print("\nby size tier (spend incl. pump fee):")
for t in sorted({r["tier"] for r in rows}, key=str):
    v = [r for r in rows if r["tier"] == t]
    print(f"   {t!s:6} {len(v):4} tokens {sum(r['pnl'] for r in v):+8.2f} SOL, ROI {sum(r['pnl'] for r in v) / sum(r['size'] for r in v):+.1%}, win {sum(r['pnl'] > 0 for r in v) / len(v):.0%}, median {S.median(r['pnl'] for r in v):+.3f}, sells med {S.median(r['n'] for r in v)}")
print("\ntiers used per day:", {d: dict(collections.Counter(r["tier"] for r in rows if r["d"] == d).most_common(6)) for d in sorted({r["d"] for r in rows})})
w = sorted(rows, key=lambda r: -r["pnl"])
print("\nbest 5:", [(r["m"][:6], round(r["pnl"], 2), r["tier"], r["n"]) for r in w[:5]], "| worst 5:", [(r["m"][:6], round(r["pnl"], 2), r["tier"], r["n"]) for r in w[-5:]])
tot = sum(r["pnl"] for r in rows); print(f"SOL-quoted total {tot:+.2f}; without best 2 {tot - w[0]['pnl'] - w[1]['pnl']:+.2f}; without best 10 {tot - sum(r['pnl'] for r in w[:10]):+.2f}")
json.dump(rows, open("/home/moiz/sniper/ops/overnight/dkmjeg/exits_rows.json", "w"))
