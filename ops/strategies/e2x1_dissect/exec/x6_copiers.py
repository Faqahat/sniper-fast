#!/usr/bin/env python3
"""Q5 copier census + follower value (MEASURED on tape, D1 lots; D0 check).
Copier = wallet that buys his token within 0..2 slots AFTER his buy (tape order) and sells within 0..3 slots AFTER his sell.
Follower value: constant-product curve state depends only on net SOL in the curve, so removing the copiers' net SOL (buys in curve
minus sells out of curve) that sits in the curve at his sell gives the counterfactual curve vSOL -> his counterfactual proceeds.
Out: sniper-data/e2x1_dissect/exec/x6.txt, x6.pkl"""
import sys, pickle, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/exec")
import numpy as np, xlib as X
R = pickle.load(open(f"{X.X}/x4.pkl", "rb"))
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
res = {}
for D in ("D1", "D0"):
    RR = [r for r in R if r["day"] == D and r["sells"] and not r["swap"]]
    cb = collections.Counter(); cs = collections.Counter(); seen = collections.Counter(); bsz = collections.defaultdict(list)
    for r in RR:
        s0 = r["sells"][0]; ws = set()
        for p in r["path"]:
            if p[6]: continue
            ws.add(p[2])
        for w in ws:
            seen[w] += 1
            b = [p for p in r["path"] if p[2] == w and p[3] and p[0] - r["s"] <= 2]
            sl = [p for p in r["path"] if p[2] == w and not p[3] and (p[0], p[1]) > (s0["s"], s0["i"]) and p[0] - s0["s"] <= 3]
            if b: cb[w] += 1; bsz[w].append(b[0][4] / r["cost"])
            if b and sl: cs[w] += 1
    cop = [w for w, n in cs.most_common() if n >= 20 and n / max(cb[w], 1) >= 0.5]
    P(f"===== {D}: lots {len(RR)}; copier census (buy <=2 slots after his buy AND sell <=3 slots after his sell, >=20 lots, >=50% of its quick buys)")
    for w in cop[:25]:
        P(f"  {w}  co-buy {cb[w]:4}  co-buy+co-sell {cs[w]:4}  ({100*cs[w]/cb[w]:3.0f}%)  size/his p50 {np.median(bsz[w]):.2f}  lots seen {seen[w]}")
    COP = set(cop) - {X.SIB}
    rows = []
    for r in RR:
        s0 = r["sells"][0]; f = 0.0; fb = 0.0; n_fb = 0; nn = 0; first2 = 0.0
        vpre = None; vtpre = None
        for p in r["path"]:
            if (p[0], p[1]) >= (s0["s"], s0["i"]): break
            if p[2] in COP:
                f += p[4] if p[3] else -p[4]
                if p[3]: fb += p[4]; n_fb += 1
                if p[3] and p[0] - r["s"] <= 2: first2 += p[4]
        pre = [p for p in r["path"] if (p[0], p[1]) < (s0["s"], s0["i"])]
        # curve state just before his sell
        v = pre[-1][5] if pre else r["v0"]
        k = None
        rows.append(dict(lot=r["lot"], bot=r["bot"], pnl=r["pnl"], cost=r["cost"], f=f, fb=fb, n_fb=n_fb, first2=first2, v=v, tok=r["tok"], net=s0["net"], fees=(r["fbps"] + r["cbps"]) / 1e4, mint=r["mint"], sig=r["buy_sig"], ssig=s0["sig"]))
    # counterfactual: need vtok: use k = vsol*vtok const for pump curve (vsol0=30 SOL, vtok0=1.073e15) -> k = 3.219e16 (SOL*raw)
    K = 30.0 * 1073000000000000
    for x in rows:
        def sell(v, tok): vt = K / v; return v * tok / (vt + tok)
        v2 = max(x["v"] - x["f"], 1.0)
        x["cf_net"] = sell(v2, x["tok"]) * (1 - x["fees"]); x["act_net"] = sell(x["v"], x["tok"]) * (1 - x["fees"])
        x["delta"] = x["act_net"] - x["cf_net"]
    tot = sum(x["pnl"] for x in rows); dl = sum(x["delta"] for x in rows)
    P(f"  copier set used ({len(COP)} wallets, sibling excluded). Lots with a copier buy within 2 slots: {sum(x['first2']>0 for x in rows)} of {len(rows)}")
    P(f"  his lot P&L {tot:+.3f} SOL; copiers' net SOL in the curve at his sell: p50 {np.median([x['f'] for x in rows]):.3f}, mean {np.mean([x['f'] for x in rows]):.3f}")
    P(f"  check: model sell vs his actual net proceeds, median ratio {np.median([x['act_net']/x['net'] for x in rows if x['net']>0]):.4f}")
    P(f"  value of copiers' SOL to him (actual - counterfactual proceeds) = {dl:+.3f} SOL  -> P&L without copiers {tot-dl:+.3f}")
    for b in ("FRESH", "MINUTE", "OLD"):
        v = [x for x in rows if x["bot"] == b]; P(f"    {b:6} lots {len(v):4} P&L {sum(x['pnl'] for x in v):+8.3f}  copier value {sum(x['delta'] for x in v):+7.3f}  without {sum(x['pnl']-x['delta'] for x in v):+8.3f}")
    a = [x for x in rows if x["first2"] > 0]; b_ = [x for x in rows if x["first2"] == 0]
    P(f"  split: lots WITH copier buys <=2 slots: n={len(a)} P&L {sum(x['pnl'] for x in a):+.3f} ({1000*np.mean([x['pnl'] for x in a]):+.1f} mSOL/lot, win {100*np.mean([x['pnl']>0 for x in a]):.0f}%) | WITHOUT: n={len(b_)} P&L {sum(x['pnl'] for x in b_):+.3f} ({1000*np.mean([x['pnl'] for x in b_]):+.1f} mSOL/lot, win {100*np.mean([x['pnl']>0 for x in b_]):.0f}%)")
    res[D] = dict(cop=cop, rows=rows)
pickle.dump(res, open(f"{X.X}/x6.pkl", "wb"))
open(f"{X.X}/x6.txt", "w").write("\n".join(out) + "\n")
