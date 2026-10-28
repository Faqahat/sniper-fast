#!/usr/bin/env python3
"""migrate agent, step 5: (a) entry mechanics table (react vs pre-send: fill share, late/guard/pre_miss, fill vSOL, tries);
(b) EV threshold: per V and failure-exit rule, measured mean P&L of graduated vs failed entries (TRAIN) -> p* where EV = 0,
and the realized P&L of 'p120 >= p*' on TEST; (c) exit timing on graduated entries (mig+N)."""
import pickle, numpy as np, collections
from mlib import D, TRAIN, TEST
F = pickle.load(open(D + "/feat.pkl", "rb")); meta = F["meta"]; PP = pickle.load(open(D + "/feat_p.pkl", "rb"))
def load(tag):
    S = pickle.load(open(D + f"/sim_{tag}.pkl", "rb")); R = S["R"]; EX = S["EXITS"]
    I = np.array([r["i"] for r in R]); return S, R, EX, I
print("== (a) ENTRY MECHANICS, size 1 SOL, first crossings, all days (share of landing-delay samples) ==")
print("mode  V    rows  fill%  late%  guard%  pre_miss%  pre-fill share  mean fill vSOL  tries/row  entries that graduate%")
for tag in ("react_1.0", "pre_1.0"):
    S, R, EX, I = load(tag)
    for V in (85, 90, 95, 100, 105, 108):
        a = [r for r in R if meta[r["i"]]["V"] == V and meta[r["i"]]["ncross"] == 0]
        if not a: continue
        w = lambda k: np.mean([r["why"].get(k, 0) / 10 for r in a])
        fl = np.array([r["fill"] for r in a]); g = np.array([meta[r["i"]]["grad"] for r in a])
        print(f"{tag[:5]:5s} {V:3d}  {len(a):5d}  {fl.mean():5.1%}  {w('late'):5.1%}  {w('guard'):6.1%}  {w('pre_miss'):8.1%}  {np.mean([r['pre_share'] for r in a]):14.1%}"
              f"  {np.nanmean([r['fill_vs'] for r in a]):14.1f}  {np.mean([r['tries'] for r in a]):9.1f}  {(fl * g).sum() / max(fl.sum(), 1e-9):8.1%}")
# crossings that the crossing trade itself completes (not entrable)
print("\ncrossings completed by the crossing trade itself (not entrable), first crossings, all days:")
for V in (85, 90, 95, 100, 105, 108):
    a = [r for r in meta if r["V"] == V and r["ncross"] == 0 and not r["edge"]]
    print(f"  V={V}: {len(a)} crossings, {np.mean([r['cross_completes'] for r in a]):.1%} self-completing")

print("\n== (b) EV THRESHOLD (react, 1 SOL, first crossings, exit mig+2): TRAIN mean P&L per entry if graduated (G) / failed (L) -> p* = L/(G+L); TEST P&L at p120>=p* ==")
S, R, EX, I = load("react_1.0")
res = np.array([r["res"] for r in R]); fill = np.array([r["fill"] for r in R]); V = np.array([meta[i]["V"] for i in I])
day = np.array([meta[i]["day"] for i in I]); grad = np.array([meta[i]["grad"] for i in I]); nc = np.array([meta[i]["ncross"] for i in I])
p = PP["p120"][I]
for V_ in (90, 95, 100, 105, 108):
    for st in (None, 0.10, 0.20, "pd0.5"):
        for to in (30, 120, 600):
            xi = EX.index((2, st, to))
            s = (V == V_) & (nc == 0) & np.isin(day, TRAIN) & (fill > 0)
            G = np.nanmean(res[s & grad, xi] / fill[s & grad]); L = -np.nanmean(res[s & ~grad, xi] / fill[s & ~grad])
            pstar = L / (G + L) if G + L > 0 else np.nan
            t = (V == V_) & (nc == 0) & np.isin(day, TEST) & (p >= pstar)
            tt = (V == V_) & (nc == 0) & np.isin(day, TEST)
            print(f"  V={V_} stop={str(st):5s} to={to:3d}s: G {G:+.4f} L {L:+.4f} p* {pstar:.2f} | train base grad rate {grad[s].mean():.0%} | TEST p120>=p*: {np.nansum(res[t, xi]) / 2:+6.2f}/day ({fill[t].sum() / 2:.0f} entries/d)  all: {np.nansum(res[tt, xi]) / 2:+6.2f}/day")
print("\n== (c) EXIT TIMING on graduated entries (react, 1 SOL, V=100/105, no stop, to 600): mean P&L per entry by mig+N (train | test) ==")
for V_ in (95, 100, 105):
    line = f"  V={V_}: "
    for n in (0, 2, 5, 20, 100):
        xi = EX.index((n, None, 600))
        s = (V == V_) & (nc == 0) & grad & (fill > 0)
        a = s & np.isin(day, TRAIN); b = s & np.isin(day, TEST)
        line += f"mig+{n}: {np.nansum(res[a, xi]) / fill[a].sum():+.4f}|{np.nansum(res[b, xi]) / fill[b].sum():+.4f}  "
    print(line)
print("\n== pool-open sniped share (price at mig+2 < open) among graduated entrable first crossings, by V ==")
for V_ in (90, 100, 105):
    a = [r for r in R if meta[r["i"]]["V"] == V_ and meta[r["i"]]["ncross"] == 0 and meta[r["i"]]["grad"]]
    print(f"  V={V_}: {np.mean([r.get('sniped', False) for r in a]):.0%} of {len(a)}")
