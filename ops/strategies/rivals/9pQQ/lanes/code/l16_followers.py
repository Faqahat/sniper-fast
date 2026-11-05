#!/usr/bin/env python3
"""LANES step 16: follower wallets of 9pQQ (train days 10-28..10-30): wallets whose buys land within 3 slots after a 9pQQ buy on the same
token at least 30 times and in >=10 % of their buys. Then forward moves of every decision moment with 9pQQ AND these followers removed.
-> lanes/followers.json, lanes/momfwdF_<run>.npy"""
import sys, json, numpy as np, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/rivals/9pQQ/lanes/code")
import llib
K, V = llib.K, llib.V
if sys.argv[1] == "list":
    cnt = collections.Counter(); tot = collections.Counter()
    for run in llib.RUNS[:3]:
        t = llib.load(run)
        isb = t.tok > 0; own = (t.u == t.wid) & isb
        for m in range(len(t.mints)):
            a, b = t.ms[m], t.ms[m + 1]
            if not own[a:b].any(): continue
            S = t.s[a:b]; U = t.u[a:b]; B = isb[a:b]; ob = np.nonzero(own[a:b])[0]
            for j in ob:
                e = int(np.searchsorted(S, S[j] + 3, side="right"))
                for u in set(U[j + 1:e][B[j + 1:e]]):
                    if u != t.wid: cnt[t.users[u]] += 1
        uu, cc = np.unique(t.u[isb], return_counts=True)
        for u, c in zip(uu, cc): tot[t.users[u]] += int(c)
        del t
    F = {u: (c, tot[u]) for u, c in cnt.items() if c >= 30 and c >= 0.1 * tot[u]}
    json.dump(dict(sorted(F.items(), key=lambda x: -x[1][0])), open("/home/moiz/sniper/ops/strategies/rivals/9pQQ/lanes/followers.json", "w"), indent=0)
    print("followers", len(F), sorted(F.items(), key=lambda x: -x[1][0])[:10])
else:
    run = sys.argv[1]; F = set(json.load(open("/home/moiz/sniper/ops/strategies/rivals/9pQQ/lanes/followers.json")))
    z = np.load(f"{llib.D}/mom_{run}.npz"); ids = z["ids"]; t = llib.load(run)
    fol = np.isin(t.u, np.array([np.searchsorted(t.users, f) for f in F if f in set(t.users)]))
    rem = np.where((t.u == t.wid) | fol, t.tok.astype(float), 0.0)       # tokens taken out of the curve by 9pQQ + followers
    cum = np.cumsum(rem); st = t.ms[t.m]; base = np.where(st > 0, cum[np.maximum(st - 1, 0)], 0.0); held = cum - base
    cpa = t.cpost.astype(float) + held; P = (K / (cpa + V)) / (cpa + V)
    HS = (1, 5, 20, 80, 300); out = np.full((len(ids), len(HS)), np.nan, np.float32)
    for k, (m, row) in enumerate(ids):
        a, b = t.ms[m], t.ms[m + 1]; s0 = t.s[row]
        for h, H in enumerate(HS):
            e = a + int(np.searchsorted(t.s[a:b], s0 + H, side="right")) - 1
            # followers' tokens bought before the moment stay in (only remove those after the moment): rebase
            out[k, h] = (P[e] / P[row] - 1) if True else np.nan
    np.save(f"{llib.D}/momfwdF_{run}.npy", out); print(run, "done", flush=True)
