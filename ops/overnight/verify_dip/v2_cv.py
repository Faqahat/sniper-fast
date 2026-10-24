#!/usr/bin/env python3
# Independent re-run of dip/dipcv.py (snapshot in v2_snap/) that keeps every out-of-fold score, so the "none" / "filter" /
# "thr" direct modes, the guard, per-block totals, bootstraps and seeds can all be computed from one training pass.
# Same logic and RNG order as dipcv.py: rows sorted by bt+age, K contiguous blocks, va = random 15% of training blocks
# (np.random.default_rng(VA_SEED) drawn block by block), GBDT 300 rounds lr 0.05 depth 3 (fit seed GB_SEED), thr = quantile(f[va], 1-Q).
# env: EVF, EXIT, LATS, Q (0.05), K (6), DIRECT_FILE (rows restricted to labelled ones, as dipcv does), VA_SEED (1), GB_SEED (0),
#      OUT (jsonl, one line per test row: LAT, block, m, age, run, f, thr, thr_d, pnl, px, d)
import sys, os, json, gzip
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "v2_snap"))
import gbdt_np as G
import dipcv as C          # snapshot copy: FK, fv (main guarded)
EVF = os.environ["EVF"]; K = int(os.environ.get("K", "6")); EXIT = os.environ.get("EXIT", "2"); Q = float(os.environ.get("Q", "0.05"))
VA_SEED = int(os.environ.get("VA_SEED", "1")); GB_SEED = int(os.environ.get("GB_SEED", "0"))
DIR = json.load(open(os.environ["DIRECT_FILE"])) if os.environ.get("DIRECT_FILE") else None
R = [json.loads(l) for l in gzip.open(EVF, "rt")]
R.sort(key=lambda r: r["bt"] + r["age"])
fo = open(os.environ["OUT"], "w")
for LAT in os.environ.get("LATS", "35,50,75").split(","):
    rows = [r for r in R if LAT in r["pnl"] and EXIT in r["pnl"][LAT]]
    if DIR is not None: rows = [r for r in rows if f'{r["m"]}|{r["age"]}' in DIR]
    X = np.array([C.fv(r) for r in rows]); P = np.array([r["pnl"][LAT][EXIT] for r in rows]); y = (P > 0).astype(float)
    n = len(rows); blk = np.minimum((np.arange(n) * K) // n, K - 1); rng = np.random.default_rng(VA_SEED)
    dmask = np.array([DIR[f'{r["m"]}|{r["age"]}'] == 1 for r in rows]) if DIR is not None else np.zeros(n, bool)
    for b in range(K):
        trall = blk != b; va = trall & (rng.random(n) < 0.15); tr = trall & ~va; te = blk == b
        Bm = G.binize(X, tr); trees, f = G.fit(Bm, y, tr, va, rounds=300, lr=0.05, depth=3, seed=GB_SEED)
        thr = float(np.quantile(f[va], 1 - Q))
        thr_d = float(np.quantile(f[va & dmask], 1 - Q)) if dmask.any() else float("nan")
        for q in np.where(te)[0]:
            r = rows[q]
            fo.write(json.dumps(dict(LAT=LAT, block=b, m=r["m"], age=r["age"], run=r["run"], bt=r["bt"], f=float(f[q]), thr=thr, thr_d=thr_d,
                                     pnl=float(P[q]), px=r.get("px", {}).get(LAT, 1.0), d=int(dmask[q]), seller=r["seller"], sell=r["sell"],
                                     **({"pall": r["pnl"][LAT]} if os.environ.get("ALLP") else {}))) + "\n")
        sel = te & (f >= thr)
        print(f"LAT {LAT} block {b}: n_test {te.sum()} picks {sel.sum()} total {P[sel].sum():+.2f} | direct picks {(sel & dmask).sum()} total {P[sel & dmask].sum():+.2f}", flush=True)
fo.close()
