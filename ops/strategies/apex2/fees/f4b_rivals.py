#!/usr/bin/env python3
"""APEX-FEES step 4b: rival attempt accounting (first-rate per ATTEMPTED launch, copies, fail fees) + within-wallet pay effect.
Also writes sample sigs per rival for f3_txshape.py (fees/rival_sigs.json)."""
import sys, json, collections, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/apex2/fees")
import fl
RIV = ["6Z91Dgiz", "dKMjeGJ4", "AHwJSnFN", "8RvtT818", "4yFAz7dp", "2mqrindM", "FiFawHqx", "CWiNFAEk", "4zT7uCnA", "BXB7FF4m"]
CL = ["AgaveBam", "JitoLabs", "HarmonicAgave", "HarmonicFiredancer", "Firedancer", "FireBAM"]
C, L = fl.load(); N = len(C["run"])
u8 = np.array([s[:8] for s in C["user"]], object); s8 = np.array([s[:8] for s in C["signer"]], object)
tot = C["prio"] + C["tips"]
G = collections.defaultdict(list)
for k in np.flatnonzero((C["role"] == "buy") & (C["so"] == 0) & (C["rank"] >= 0)): G[C["mint"][k]].append(k)
for v in G.values(): v.sort(key=lambda k: C["i"][k])
sig_out = {}
print("wallet | launches attempted | landed any | landed cs | FIRST in cs | first per attempt | txs per attempted launch p50/p90 | fails on launches it landed / not | fail fee p50 mSOL (prio on fails) | first-attempt cs share | client mix of attempts")
for w in RIV:
    mw = np.flatnonzero((u8 == w) | (s8 == w))
    att = collections.defaultdict(list)
    for k in mw:
        if C["role"][k] in ("buy", "fail", "noop") and C["so"][k] in (0, 1): att[C["mint"][k]].append(k)
    landed = {m for m, ks in att.items() if any(C["role"][k] == "buy" for k in ks)}
    lcs = {m for m, ks in att.items() if any(C["role"][k] == "buy" and C["so"][k] == 0 for k in ks)}
    first = {m for m in lcs if G[m] and (u8[G[m][0]] == w or s8[G[m][0]] == w)}
    ntx = [len(ks) for ks in att.values()]
    fl_l = sum(1 for m, ks in att.items() for k in ks if C["role"][k] == "fail" and m in landed)
    fl_n = sum(1 for m, ks in att.items() for k in ks if C["role"][k] == "fail" and m not in landed)
    fk = [k for ks in att.values() for k in ks if C["role"][k] == "fail"]
    cs0 = np.mean([min(C["so"][k] for k in ks) == 0 for ks in att.values()])
    cm = collections.Counter(C["client"][min(ks, key=lambda k: (C["so"][k], C["i"][k]))] for ks in att.values()).most_common(3)
    print(f"{w} | {len(att)} | {len(landed)} | {len(lcs)} | {len(first)} | {len(first)/max(len(att),1):.0%} | {np.median(ntx):.0f}/{np.percentile(ntx,90):.0f} | "
          f"{fl_l}/{fl_n} | {np.median(C['fee'][fk])/1e6 if fk else float('nan'):.3f} | {cs0:.0%} | {cm}")
    lb = [k for k in mw if C["role"][k] == "buy" and C["so"][k] == 0]
    fb = [k for k in mw if C["role"][k] == "fail"]
    rng = np.random.default_rng(1)
    sig_out[w] = [C["sig"][k] for k in rng.choice(lb, min(8, len(lb)), replace=False)] + [C["sig"][k] for k in rng.choice(fb, min(3, len(fb)), replace=False)] if fb else [C["sig"][k] for k in rng.choice(lb, min(8, len(lb)), replace=False)]
json.dump(sig_out, open("/home/moiz/sniper-data/apex2/fees/rival_sigs.json", "w"))

# within-wallet: same bot paying more than its own usual -> first more often? (contested create slots, wallets with >= 100 such buys)
print("\nWithin-wallet effect of own pay on being first (contested create slots; wallet fixed effects; logit-free linear prob.) [M]")
print("client | wallets | buys | d first-rate per doubling of OWN pay | d per doubling of strongest OTHER pay")
rows = []
for m, v in G.items():
    if len(v) < 2: continue
    for r, k in enumerate(v):
        oth = max(tot[x] for x in v if x != k)
        rows.append((C["user"][k], C["client"][k], r == 0, np.log2(tot[k] + 1e4), np.log2(oth + 1e4)))
for cl in CL + ["*"]:
    R = [x for x in rows if cl == "*" or x[1] == cl]
    by = collections.defaultdict(list)
    for x in R: by[x[0]].append(x)
    Y, X1, X2 = [], [], []; nw = 0
    for u, xs in by.items():
        if len(xs) < 100: continue
        nw += 1
        y = np.array([x[2] for x in xs], float); a = np.array([x[3] for x in xs]); b = np.array([x[4] for x in xs])
        if a.std() < 0.05: continue
        Y.append(y - y.mean()); X1.append(a - a.mean()); X2.append(b - b.mean())
    if not Y: continue
    y = np.concatenate(Y); X = np.c_[np.concatenate(X1), np.concatenate(X2)]
    bb, *_ = np.linalg.lstsq(X, y, rcond=None)
    print(f"{cl} | {len(Y)} | {len(y):,} | {bb[0]:+.3f} | {bb[1]:+.3f}")
