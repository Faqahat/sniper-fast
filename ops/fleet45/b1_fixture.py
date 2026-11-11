#!/usr/bin/env python3
"""dip46 B1: the Rust parity fixture (testdata/dip46_b1_parity.json.zst) from the push4-audit NEW tape.

  b1_fixture.py [--n-hot 30] [--n-rand 20] [--max-trades 1500]

Picks tokens (half where the frozen decoder passes often, half at random), takes their real trades (chain order), builds every
token-slot query (the slot after each trade slot, as p4_snap.py 'all'), the reference features (b1_lib.features_at), the frozen
scores by sklearn itself (the offline scorer the engine must match), and the 8-slot window outcome (first >= 10% dump, position-26
paper, 3-slot exit; b1_lib.outcome). Also checks the reference features against the audit's snap_all.parquet rows of the same
(token, slot): every feature except n_prev_dumps / last_dump_* (the audit's dump table starts at r75's end) must agree.
"""
import argparse, os, sys, json, pickle
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import b1_lib as B

NEW = os.path.expanduser("~/sniper-data/push4-audit/new")
ap = argparse.ArgumentParser()
ap.add_argument("--n-hot", type=int, default=30); ap.add_argument("--n-rand", type=int, default=20); ap.add_argument("--max-trades", type=int, default=1500)
ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../testdata/dip46_b1_parity.json.zst"))
a = ap.parse_args()

o = pickle.load(open(os.path.expanduser("~/sniper-data/push4-audit/frozen_models.pkl"), "rb"))["final"]; dec, reg = o["dec"], o["reg"]
X = pd.read_parquet(NEW + "/snap_all.parquet"); X["last_buy"] = X.last_buy.astype(int)
X["score"] = dec.predict_proba(X[B.F0])[:, 1]
t = pd.read_parquet(NEW + "/trades.parquet", columns=["s", "i", "k", "mint", "user", "buy", "sol", "tok", "vsol", "vtok"])
t["mint"] = t.mint.astype(str); t["user"] = t.user.astype(str)
cnt = t.mint.value_counts()
okm = set(cnt[(cnt >= 40) & (cnt <= a.max_trades)].index)
g = X[X.mint.isin(okm)].groupby("mint").score.apply(lambda v: (v >= 0.2).sum()).sort_values(ascending=False)
rng = np.random.default_rng(46)
hot = list(g.index[: a.n_hot]); rest = [m for m in okm if m not in set(hot)]; rest.sort()
mints = hot + list(rng.choice(rest, size=a.n_rand, replace=False))
lau = pd.read_parquet(NEW + "/launch.parquet").drop_duplicates("mint").set_index("mint")
T = t[t.mint.isin(set(mints))].sort_values(["s", "i", "k"]).reset_index(drop=True)
print("tokens", len(mints), "trades", len(T), "hot rows dec>=0.2:", int(g[hot].sum()), flush=True)

users = {u: n for n, u in enumerate(pd.unique(T.user))}; mi = {m: n for n, m in enumerate(mints)}
smax = T.groupby("s").i.max().to_dict()
rows = []; outs = []; cmp = []
for m in mints:
    tt = T[T.mint == m]
    tr = [(int(s), int(i), int(k), str(u), bool(b), int(sol), int(tok), int(vs), int(vt)) for s, i, k, u, b, sol, tok, vs, vt in
          zip(tt.s, tt.i, tt.k, tt.user, tt.buy, tt.sol, tt.tok, tt.vsol, tt.vtok)]
    cs = int(lau.cslot[m]) if m in lau.index else None; cr = str(lau.creator[m]) if m in lau.index else None
    dumps = B.find_dumps_one(tr)
    for qs in sorted(set(r[0] + 1 for r in tr)):
        f = B.features_at(tr, qs, cs, cr, dumps)
        if f is None: continue
        rows.append((m, qs, f))
        oc = B.outcome(tr, dumps, qs, 8, smax)
        outs.append(oc)
F = pd.DataFrame([r[2] for r in rows], columns=B.F0)
p = dec.predict_proba(F[B.F0])[:, 1]; F["score"] = p; rr = reg.predict(F[B.LITE])
M = B.Model(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../testdata/dip46_b1_model.json"))
mx = 0.0
for k in range(0, len(rows), 7):
    pp, r2 = M.score(rows[k][2]); mx = max(mx, abs(pp - p[k]), abs(r2 - rr[k]) if r2 is not None else 0.0)
print("rows", len(rows), "dec>=0.2", int((p >= 0.2).sum()), "b0 pass (>= 2 mSOL)", int(((p >= 0.2) & (rr >= 0.002)).sum()), "| JSON scorer vs sklearn max diff", mx,
      "| windows with a fill", sum(1 for x in outs if x is not None), flush=True)
# the reference vs the audit's own rows
R = pd.DataFrame(dict(mint=[r[0] for r in rows], s=[r[1] for r in rows])); R = pd.concat([R, F[B.F0]], axis=1)
J = R.merge(X[["mint", "s"] + B.F0], on=["mint", "s"], suffixes=("", "_a"))
print("reference vs audit snap_all: joined rows", len(J), "of", len(R))
for c in B.F0:
    d = np.abs(J[c].astype(float) - J[c + "_a"].astype(float)); rel = d / np.maximum(1e-12, np.abs(J[c + "_a"].astype(float)))
    bad = int(((d > 1e-9) & (rel > 1e-9)).sum())
    if bad: print(f"   {c}: {bad} rows differ (max abs {d.max():.3g})")
js = dict(note="dip46 B1 parity fixture: real trades of the push4-audit NEW tape (chain order), reference features (ops/fleet45/b1_lib.py), sklearn scores",
          mints=[dict(mint=m, cslot=int(lau.cslot[m]) if m in lau.index else None, creator=str(lau.creator[m]) if m in lau.index else None) for m in mints],
          users=list(users), trades=[[mi[m], int(s), int(i), int(k), users[u], int(b), int(sol), int(tok), int(vs), int(vt)] for s, i, k, m, u, b, sol, tok, vs, vt in
                                     zip(T.s, T.i, T.k, T.mint, T.user, T.buy, T.sol, T.tok, T.vsol, T.vtok)],
          rows=[[mi[r[0]], r[1], r[2], float(p[k]), float(rr[k]) if p[k] >= 0.2 else None,
                 None if outs[k] is None else [outs[k]["dump"][0], outs[k]["dump"][1], outs[k]["dump"][2], outs[k]["es"], outs[k]["ei"], outs[k]["paper"], outs[k]["lb"], outs[k]["nbuy"]]]
                for k, r in enumerate(rows)])
import subprocess
raw = json.dumps(js, separators=(",", ":")).encode()
subprocess.run(["zstd", "-19", "-q", "-f", "-o", a.out], input=raw, check=True)
print("wrote", os.path.abspath(a.out), os.path.getsize(a.out), "bytes")
