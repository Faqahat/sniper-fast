#!/usr/bin/env python3
"""LIM step 3 (read-only): tables for the counterfactual guard policies on our live regular fires (data/lim/fires_cf.pkl).
Net per fire = curve P&L (exact replay at the measured position) - tx costs (fill 3.52 mSOL = buy 1.75 + sell 1.77,
failed fire 0.53; MEASURED means, dv8 l2). Exits: 'ours' = the run's hold timer (5/6/19 slots); 'his' = haqq's DIP-lot hold
distribution (pos.pkl, 10-23..10-27, from his buy; snapped to the grid, >65 -> 65); h15 = his median.
Out: data/lim/l3.txt"""
import pickle, sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_strat")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/lim"
CF, CX = 3.52e-3, 0.53e-3
G = [("+5% (live)", 0.05), ("+10%", 0.10), ("+15%", 0.15), ("+20%", 0.20), ("+30%", 0.30), ("none", 9.0)]
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)


def his_weights(HG):
    import hs_lib as H
    Pz = pickle.load(open("/home/moiz/sniper-data/haqq_strat/pos.pkl", "rb"))
    B, Lt = Pz["buys"], Pz["lots"]
    h = [Lt[b["lot_ix"]]["close_slot"] - b["slot"] for b in B if b["w"] == "haqq" and H.etype(b) == "DIP" and Lt[b["lot_ix"]]["close_slot"] is not None]
    g = np.array(HG); w = collections.Counter()
    for x in h: w[int(g[np.argmin(np.abs(g - min(x, 65)))])] += 1
    tot = sum(w.values()); return {k: v / tot for k, v in w.items()}


def boot(v, n=2000, seed=3):
    v = np.asarray(v, float); g = np.random.default_rng(seed)
    s = [v[g.integers(0, len(v), len(v))].sum() for _ in range(n)]
    return np.percentile(s, 5), np.percentile(s, 95)


def net(r, g, ex, fo, W):
    fill = r["need"] <= 1 + g + 1e-9
    if not fill: return -CX, False
    if ex == "ours": p = r["pn"][(r["hold"], fo)]
    elif ex == "his": p = sum(w * r["pn"][(h, fo)] for h, w in W.items())
    else: p = r["pn"][(ex, fo)]
    return p - CF, True


def main():
    R = pickle.load(open(f"{OUT}/fires_cf.pkl", "rb"))
    R = [r for r in R if not r["mayhem"]]
    HG = sorted({h for r in R for (h, fo) in r["pn"]} & {2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50, 65})
    W = his_weights(HG)
    P("# Counterfactual fill policies on OUR live regular fires at their MEASURED landed positions (exact curve replay)")
    P(f"fires {len(R)} (mayhem excluded: {sum(1 for r in pickle.load(open(f'{OUT}/fires_cf.pkl','rb')) if r['mayhem'])}); live fills {sum(r['out']=='fill' for r in R)}")
    ok = sum((r["need"] <= 1.05 + 1e-9) == (r["out"] == "fill") for r in R)
    P(f"check: guard +5% on tape reproduces live fill/fail on {ok}/{len(R)} fires ({100*ok/len(R):.1f}%)")
    lf = [r for r in R if r["out"] == "fill" and r["realized"] is not None]
    P(f"check: live fills n={len(lf)}: realized wallet (incl. tx costs) {sum(r['realized'] for r in lf):+.3f} SOL; replay 'ours' exit curve P&L {sum(r['pn'][(r['hold'],1.0)] for r in lf):+.3f}"
      f" - costs {len(lf)*CF:.3f} = {sum(r['pn'][(r['hold'],1.0)] for r in lf)-len(lf)*CF:+.3f}")
    P(f"haqq DIP hold weights (slots from his buy): " + ", ".join(f"{h}:{w:.2f}" for h, w in sorted(W.items())))
    P("\n## need = tokens at post-dump state / tokens at our landed state (1.05 = our guard). Distribution, failed fires only")
    fl = np.array([r["need"] for r in R if r["out"] == "fail"])
    P("p10/25/50/75/90: " + " / ".join(f"{x:.3f}" for x in np.percentile(fl, [10, 25, 50, 75, 90])) + f"; share <=1.10 {np.mean(fl<=1.10):.2f}, <=1.15 {np.mean(fl<=1.15):.2f}, <=1.20 {np.mean(fl<=1.20):.2f}, <=1.30 {np.mean(fl<=1.30):.2f}")
    for ex in ("ours", "his", 15, 2):
        P(f"\n## Policy x followers, exit = {ex}  (SOL net of tx costs, all {len(R)} fires; delta vs live guard; 90% bootstrap of delta)")
        P("| guard | fills | fol 1.0 total | delta vs +5% [90%] | per extra fill mSOL | fol 0.9 total | delta | fol 0.8 total | delta |")
        P("|---|---|---|---|---|---|---|---|---|")
        base = {fo: [net(r, 0.05, ex, fo, W)[0] for r in R] for fo in (1.0, 0.9, 0.8)}
        for nm, g in G:
            cells = []; nf = 0
            for fo in (1.0, 0.9, 0.8):
                v = [net(r, g, ex, fo, W) for r in R]; nf = sum(x[1] for x in v)
                tot = sum(x[0] for x in v); d = np.array([x[0] for x in v]) - np.array(base[fo])
                if fo == 1.0:
                    lo, hi = boot(d); extra = nf - sum(r["need"] <= 1.05 + 1e-9 for r in R)
                    cells.append(f"{tot:+.3f} | {d.sum():+.3f} [{lo:+.2f}..{hi:+.2f}] | {1000*d.sum()/max(extra,1):+.2f}")
                else: cells.append(f"{tot:+.3f} | {d.sum():+.3f}")
            P(f"| {nm} | {nf} | " + " | ".join(cells) + " |")
    # per day / server for the main exits
    for ex in ("ours", "his"):
        P(f"\n## Per day and server, exit = {ex}, fol 1.0 (fol 0.8 in brackets): SOL net")
        P("| day | srv | fires | live fills | +5% | +10% | +15% | +20% | none |"); P("|---|---|---|---|---|---|---|---|---|")
        for d in sorted({r["day"] for r in R}):
            for s in ("FRA", "AMS", "both"):
                v = [r for r in R if r["day"] == d and (s == "both" or r["srv"] == s)]
                if not v: continue
                cells = []
                for g in (0.05, 0.10, 0.15, 0.20, 9.0):
                    a = sum(net(r, g, ex, 1.0, W)[0] for r in v); b = sum(net(r, g, ex, 0.8, W)[0] for r in v)
                    cells.append(f"{a:+.2f} ({b:+.2f})")
                P(f"| {L.day_name(d)} | {s} | {len(v)} | {sum(r['out']=='fill' for r in v)} | " + " | ".join(cells) + " |")
    # the extra fills only: by need bucket
    P("\n## The fails a looser guard converts: curve P&L per fill by 'need' bucket (mSOL, before costs; exit ours / his / h2; fol 1.0 & 0.8)")
    P("| need (price at landing vs post-dump) | n | ours fol1 | ours fol.8 | his fol1 | his fol.8 | h2 fol1 | win% ours |"); P("|---|---|---|---|---|---|---|---|")
    edges = [(0, 1.05), (1.05, 1.10), (1.10, 1.15), (1.15, 1.20), (1.20, 1.30), (1.30, 1.50), (1.50, 99)]
    for lo, hi in edges:
        v = [r for r in R if lo < r["need"] <= hi]
        if not v: continue
        o1 = [r["pn"][(r["hold"], 1.0)] for r in v]; o8 = [r["pn"][(r["hold"], 0.8)] for r in v]
        h1 = [sum(w * r["pn"][(h, 1.0)] for h, w in W.items()) for r in v]; h8 = [sum(w * r["pn"][(h, 0.8)] for h, w in W.items()) for r in v]
        P(f"| {lo:.2f}-{hi:.2f} | {len(v)} | {1000*np.mean(o1):+.2f} | {1000*np.mean(o8):+.2f} | {1000*np.mean(h1):+.2f} | {1000*np.mean(h8):+.2f} | {1000*np.mean([r['pn'][(2,1.0)] for r in v]):+.2f} | {100*np.mean(np.array(o1)>0):.0f} |")
    open(f"{OUT}/l3.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
