#!/usr/bin/env python3
# GDM forward pipeline check: rebuild feature rows for a window INSIDE the training data with the forward pipeline
# (fwd_features.py on table_gdmfwd + our phase A/B) and compare with the training matrix gdm/feats.npz, feature by feature,
# plus the frozen LM / L scores and picks. usage: python3 -I parity.py <feats prefix built for the window>
import sys, json
import numpy as np
GDM = "/home/moiz/sniper/ops/overnight/gdm"
A = np.load(f"{GDM}/feats.npz"); MA = json.load(open(f"{GDM}/feats_meta.json")); B = np.load(sys.argv[1] + ".npz"); MB = json.load(open(sys.argv[1] + "_meta.json"))
ia = {m: i for i, m in enumerate(MA["mints"])}; common = [m for m in MB["mints"] if m in ia]
XA = A["X"][[ia[m] for m in common]]; XB = B["X"][[MB["mints"].index(m) for m in common]]
print(f"rows: forward pipeline {len(MB['mints'])}, training {sum(1 for m in MA['mints'] if A['bt'][ia[m]] >= B['bt'].min() and A['bt'][ia[m]] <= B['bt'].max()) if len(B['bt']) else 0}, common {len(common)}")
same = lambda a, b: (np.isnan(a) & np.isnan(b)) | (np.abs(np.nan_to_num(a, nan=1e30) - np.nan_to_num(b, nan=1e30)) <= 1e-9 * np.maximum(1, np.abs(np.nan_to_num(a))))
bad = [(MA["names"][j], int((~same(XA[:, j], XB[:, j])).sum())) for j in range(XA.shape[1])]
print("features with any mismatch:", [(k, n) for k, n in bad if n] or "none")
print(f"rows identical in all {XA.shape[1]} features: {int(np.all([same(XA[:, j], XB[:, j]) for j in range(XA.shape[1])], 0).sum())} / {len(common)}")
F = json.load(open("/home/moiz/sniper/ops/overnight/dryrun/frozen_gdm.json"))
def score(X, Mo, names):
    X = X[:, [names.index(k) for k in Mo["features"]]]; Bm = np.zeros(X.shape, np.int32)
    for j, e in enumerate(Mo["edges"]):
        b = np.searchsorted(np.array(e), X[:, j], side="right") + 1; b[np.isnan(X[:, j])] = 0; Bm[:, j] = b
    def tp(t):
        out = np.zeros(len(Bm)); st = [(t, np.arange(len(Bm)))]
        while st:
            n, ix = st.pop()
            if "w" in n: out[ix] = n["w"]; continue
            mk = Bm[ix, n["f"]] <= n["b"]; st.append((n["l"], ix[mk])); st.append((n["r"], ix[~mk]))
        return out
    return np.mean([Mo["F0"] + Mo["lr"] * sum(tp(t) for t in b["trees"]) for b in Mo["bag"]], 0)
for nm in ("LM", "L"):
    Mo = F["models"][nm]; sa = score(XA, Mo, MA["names"]); sb = score(XB, Mo, MB["names"])
    pa = sa >= Mo["threshold_top3"]; pb = sb >= Mo["threshold_top3"]
    print(f"{nm}: max |score diff| {np.max(np.abs(sa - sb)) if len(sa) else 0:.2e}; picks training {pa.sum()} vs forward pipeline {pb.sum()}, disagree {(pa != pb).sum()}")
