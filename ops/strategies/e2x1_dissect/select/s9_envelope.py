#!/usr/bin/env python3
"""SELECT s9: take-vs-skip inside each trigger family (FIRST buys on a token; his adds handled separately).
Envelope rows = outside trade events e with my_buys == 0 (he holds nothing yet on the mint) of a family:
  LDUMP  age < 10 s,      sell with price impact <= -5 %      LPUMP  age < 10 s,      buy impact >= +5 %
  EDUMP  age 10-120 s,    sell impact <= -5 %                 EPUMP  age 10-120 s,    buy impact >= +5 %
  MFLOW  age 2-30 min,    any trade with |impact| >= 2 %
Label = his FIRST buy within 3 slots after e (y3). Weights: positives 1, sampled negatives 25 (4 % hash sample -> unbiased).
Forward (market, no fees): g24/g141 = px change from the end of slot s+1 (our-speed entry, after his buy) to +24 / +141 slots;
f5 = from e's px to +5 slots (includes his own buy impact ~1.4 % on his picks).
Per family: base rate, his picks vs skipped; GBDT (train = before newest 6 h, val = 12 h before; TEST newest 6 h) AUC, and the
forward return of the model's rate-matched picks on TEST. Out: s9.txt, s9_scores.npz.  META=1 env: + create-time metadata features (s16) -> s9_scores1.npz"""
import sys, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect"); import dd_gbdt as G
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select")
from s4_model import MKT, auc
OUT = "/home/moiz/sniper-data/e2x1_dissect/select"
U = dict(np.load(f"{OUT}/U.npz"))
import os
META = ["host_rate", "name_len", "sym_len", "sym_upper", "name_nonascii", "name_words", "vanity_pump"]
FEATS = MKT + (META if os.environ.get("META") else [])
if os.environ.get("META"):
    Mt = np.load(f"{OUT}/meta.npz")
    for k in META: U[k] = Mt[k][U["mint"]]
tmax = U["bt"].max(); TE = U["bt"] >= tmax - 6 * 3600; VA = (U["bt"] >= tmax - 18 * 3600) & ~TE
y = U["y3"].astype(bool) & (U["my_buys"] == 0)
rowsok = (U["my_buys"] == 0) & (U["samp"] | y)
wt = np.where(y, 1.0, 25.0)
age = U["age_s"]; imp = U["imp"]; isb = U["is_buy"] > 0
FAM = {"LDUMP": (age < 10) & ~isb & (imp <= -0.05), "LPUMP": (age < 10) & isb & (imp >= 0.05),
       "EDUMP": (age >= 10) & (age < 120) & ~isb & (imp <= -0.05), "EPUMP": (age >= 10) & (age < 120) & isb & (imp >= 0.05),
       "MFLOW": (age >= 120) & (np.abs(imp) >= 0.02)}
def mean(x, w):
    ok = np.isfinite(x); return 100 * np.average(np.clip(x[ok], -1, 5), weights=w[ok]) if ok.any() else np.nan
out = {}
for nm, fm in FAM.items():
    R = fm & rowsok
    yy = y[R]; ww = wt[R]
    print(f"\n=== {nm}: events (weighted) {ww.sum():.0f}, his picks {yy.sum()}  take rate {yy.sum()/ww.sum():.4f}")
    for lab, m in (("his picks", yy), ("skipped", ~yy)):
        print(f"  {lab:10s} n={m.sum():7d}  f5 {mean(U['f5'][R][m], ww[m]):+6.2f}  g24 {mean(U['g24'][R][m], ww[m]):+6.2f}  g141 {mean(U['g141'][R][m], ww[m]):+6.2f}"
              f"  P(g24>2.5%) {np.average(U['g24'][R][m] > 0.025, weights=ww[m]):.2f}")
    X = np.column_stack([U[f].astype(np.float64) for f in FEATS])[R]; te = TE[R]; va = VA[R]; tr = ~te & ~va
    E = G.edges_of(X, tr); B = G.binize(X, E)
    M = G.fit(B, yy.astype(float), tr, va, loss="log", rounds=300, lr=0.1, depth=4, min_n=100, lam=5.0, seed=2, patience=40)
    s = G.predict(M, B)
    a_te = auc(s[te], yy[te]); print(f"  GBDT: AUC val {auc(s[va], yy[va]):.3f}  TEST {a_te:.3f}  (test his picks {yy[te].sum()})")
    imp_ = G.importance(M, len(FEATS)); print("  top features:", [(FEATS[i], round(float(imp_[i]), 3)) for i in np.argsort(-imp_)[:8]])
    # rate-matched on TEST
    st = s[te]; yt = yy[te]; wt_ = ww[te]; o = np.argsort(-st); cw = np.cumsum(wt_[o])
    for mult in (1, 3):
        k = np.searchsorted(cw, yt.sum() * mult); top = np.zeros(len(st), bool); top[o[:k]] = True
        rec = (top & yt).sum() / max(yt.sum(), 1); prec = (top & yt).sum() / max(wt_[top].sum(), 1)
        g = {k_: U[k_][R][te] for k_ in ("f5", "g24", "g141")}
        nh = top & ~yt
        print(f"  TEST model top x{mult}: recall {rec:.2f} precision {prec:.3f} | model-not-his g24 {mean(g['g24'][nh], wt_[nh]):+.2f} g141 {mean(g['g141'][nh], wt_[nh]):+.2f}"
              f" | his(test) g24 {mean(g['g24'][yt], wt_[yt]):+.2f} g141 {mean(g['g141'][yt], wt_[yt]):+.2f} | all test g24 {mean(g['g24'], wt_):+.2f}")
    out[nm] = dict(rows=np.flatnonzero(R), s=s)
np.savez(f"{OUT}/s9_scores{os.environ.get('META','')}.npz", **{f"{k}_rows": v["rows"] for k, v in out.items()}, **{f"{k}_s": v["s"] for k, v in out.items()})
