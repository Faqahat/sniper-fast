#!/usr/bin/env python3
"""Q1 landing anatomy (MEASURED). His tiered buys: trigger T (size code) -> his buy: slot gap, index gap, chain-clock ms,
by leader client of his slot and by landed copy. Same-slot probability vs T's position in its block (reaction-time estimate).
Apples-to-apples with haqq exec t7 / ours: 'dump' = previous outside trade is a sell >= 0.5 SOL within 2 slots.
Out: sniper-data/e2x1_dissect/exec/x1.txt + x1.pkl (per-lot rows)"""
import sys, collections, pickle
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/exec")
import numpy as np, xlib as X
L = X.lots(); T = X.tape()["trades"]
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
sigpos = {}
for m, tr in T.items():
    for t in tr: sigpos[t[15]] = t
def copy_of(l):
    r = l["buy_relay"]; a = l["buy_tip_amt"]
    return f"{r}:{a}"
rows = []
for l in L:
    if l["day"] not in ("D0", "D1"): continue
    ld, cl = X.leader(l["s"])
    r = dict(lot=l["lot_id"], day=l["day"], bot=l["bot"], mint=l["mint"], sig=l["buy_sig"], s=l["s"], i=l["i"], client=cl, leader=ld, copy=copy_of(l),
             frac=X.frac(l["s"], l["i"]), pnl=l["pnl"], cost=l["cost"])
    t = sigpos.get(l.get("trig_sig")) if l.get("trig_sig") else None
    if t is not None:
        r.update(ts=t[0], ti=t[1], tbuy=t[6], tsol=t[7] / 1e9, tuser=t[4], trelay=t[13], tfrac=X.frac(t[0], t[1]), gap=l["s"] - t[0],
                 igap=(l["i"] - t[1]) if l["s"] == t[0] else None, ms=X.cc(l["s"], l["i"]) - X.cc(t[0], t[1]), tclient=X.leader(t[0])[1], tsig=t[15])
    # haqq-t7 style dump: previous outside trade on the mint
    tr = T.get(l["mint"], [])
    prev = None
    for t2 in tr:
        if (t2[0], t2[1]) >= (l["s"], l["i"]): break
        if t2[16] and t2[4] != X.WAL: prev = t2
    if prev is not None:
        r.update(ps=prev[0], pi=prev[1], pbuy=prev[6], psol=prev[7] / 1e9, pms=X.cc(l["s"], l["i"]) - X.cc(prev[0], prev[1]), pgap=l["s"] - prev[0])
    rows.append(r)
pickle.dump(rows, open(f"{X.X}/x1.pkl", "wb"))
def summ(v, lab):
    if len(v) < 10: return
    ms = np.array([x["ms"] for x in v]); g = np.array([x["gap"] for x in v])
    P(f"  {lab:34} n={len(v):5} ms p25/50/75 {X.pct(ms,25):5.0f}/{X.med(ms):5.0f}/{X.pct(ms,75):5.0f}  same-slot {100*(g==0).mean():3.0f}%  +1 {100*(g==1).mean():3.0f}%  >=2 {100*(g>=2).mean():3.0f}%")
for day in ("D1", "D0"):
    R = [r for r in rows if r["day"] == day and "ms" in r]
    P(f"===== {day}: trigger (size code) -> his buy, chain clock ms (slot=212 ms), n={len(R)} tiered lots")
    summ(R, "ALL")
    for k in ("bot", "client", "copy"):
        for v in sorted(set(r[k] for r in R)): summ([r for r in R if r[k] == v], f"{k}={v}")
    summ([r for r in R if r["tbuy"]], "trigger is a buy"); summ([r for r in R if not r["tbuy"]], "trigger is a sell")
    summ([r for r in R if not r["tbuy"] and r["tsol"] >= 0.5], "trigger is a sell >=0.5 SOL")
    if day == "D1":
        S0 = [r for r in R if r["gap"] == 0]
        ig = np.array([r["igap"] for r in S0])
        P(f"  same-slot lots n={len(S0)}: index gap p10/25/50/75/90 = " + "/".join(f"{X.pct(ig,q):.0f}" for q in (10, 25, 50, 75, 90)))
        for N in (5, 10, 25, 50, 100, 200):
            P(f"    share of ALL tiered buys landing in T's slot with index gap <= {N:3}: {100*np.mean([(r['gap']==0 and r['igap']<=N) for r in R]):4.1f}%   (of same-slot: {100*(ig<=N).mean():4.1f}%)")
        msS = np.array([r["ms"] for r in S0]); P(f"    same-slot chain-clock ms p10/25/50/75/90 = " + "/".join(f"{X.pct(msS,q):.0f}" for q in (10, 25, 50, 75, 90)))
        P("  P(he lands in T's own slot) by T's position in its block (frac of block) -> where the curve drops = his reaction time")
        for a, b in ((0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, .9), (.9, 1.01)):
            v = [r for r in R if a <= r["tfrac"] < b]
            if v: P(f"    T frac {a:.1f}-{b:.1f}: n={len(v):4}  same-slot {100*np.mean([r['gap']==0 for r in v]):3.0f}%   ms p50 {X.med([r['ms'] for r in v]):4.0f}")
        P("  same, by leader client of T's slot (same-slot %, T frac <0.5 vs >=0.5)")
        for c in sorted(set(r["tclient"] for r in R)):
            v1 = [r for r in R if r["tclient"] == c and r["tfrac"] < .5]; v2 = [r for r in R if r["tclient"] == c and r["tfrac"] >= .5]
            if len(v1) + len(v2) >= 20:
                P(f"    {c:10} early T n={len(v1):4} same {100*np.mean([r['gap']==0 for r in v1]) if v1 else 0:3.0f}% | late T n={len(v2):4} same {100*np.mean([r['gap']==0 for r in v2]) if v2 else 0:3.0f}%")
        G1 = [r for r in R if r["gap"] == 1]
        f1 = np.array([r["frac"] for r in G1]); P(f"  next-slot lots n={len(G1)}: his position in the next block frac p10/25/50/75 = " + "/".join(f"{X.pct(f1,q):.2f}" for q in (10, 25, 50, 75)))
        tf1 = np.array([r["tfrac"] for r in G1]); P(f"    their T position frac p10/25/50/75 = " + "/".join(f"{X.pct(tf1,q):.2f}" for q in (10, 25, 50, 75)))
    # haqq-t7 apples-to-apples
    D = [r for r in rows if r["day"] == day and "pms" in r and not r["pbuy"] and r["psol"] >= 0.5 and r["pgap"] <= 2]
    P(f"  [t7 def] prev outside trade = sell>=0.5 SOL within 2 slots: n={len(D)}  ms p25/50/75 {X.pct([r['pms'] for r in D],25):.0f}/{X.med([r['pms'] for r in D]):.0f}/{X.pct([r['pms'] for r in D],75):.0f}  same-slot {100*np.mean([r['pgap']==0 for r in D]):.0f}%")
    for c in ("bam", "harmonic", "jito", "fd", "agave"):
        v = [r for r in D if r["client"] == c]
        if len(v) >= 10: P(f"      client={c:9} n={len(v):4} ms p50 {X.med([r['pms'] for r in v]):4.0f}  same-slot {100*np.mean([r['pgap']==0 for r in v]):3.0f}%")
    A = [r for r in rows if r["day"] == day and "pms" in r and r["pgap"] <= 2]
    P(f"  [any prev outside trade within 2 slots] n={len(A)} ms p50 {X.med([r['pms'] for r in A]):.0f} same-slot {100*np.mean([r['pgap']==0 for r in A]):.0f}%")
open(f"{X.X}/x1.txt", "w").write("\n".join(out) + "\n")
