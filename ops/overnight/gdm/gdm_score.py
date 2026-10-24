#!/usr/bin/env python3
# Score rows with the FROZEN GDM rule (dryrun/frozen_gdm.json): bag-mean GBDT score, threshold top 3%, guards.
# usage: python3 -I gdm_score.py <feats.npz> <feats_meta.json> [LM|L] -> prints picks count, writes <feats>_gdm_picks.json
import sys, json, hashlib
import numpy as np
FZ = "/home/moiz/sniper/ops/overnight/dryrun/frozen_gdm.json"
raw = open(FZ).read(); h = hashlib.sha256(raw.encode()).hexdigest()
assert h == open(FZ + ".sha256").read().strip(), "frozen file changed!"
F = json.loads(raw); nm = sys.argv[3] if len(sys.argv) > 3 else F["primary_model"]; Mo = F["models"][nm]
Z = np.load(sys.argv[1]); M = json.load(open(sys.argv[2])); X = Z["X"][:, [M["names"].index(k) for k in Mo["features"]]]
def bins(X, E):
    B = np.zeros(X.shape, np.int32)
    for j, e in enumerate(E):
        b = np.searchsorted(np.array(e), X[:, j], side="right") + 1; b[np.isnan(X[:, j])] = 0; B[:, j] = b
    return B
def tree_pred(t, B):
    out = np.zeros(len(B)); stack = [(t, np.arange(len(B)))]
    while stack:
        n, ix = stack.pop()
        if "w" in n: out[ix] = n["w"]; continue
        m = B[ix, n["f"]] <= n["b"]; stack.append((n["l"], ix[m])); stack.append((n["r"], ix[~m]))
    return out
B = bins(X, Mo["edges"])
s = np.mean([Mo["F0"] + Mo["lr"] * sum(tree_pred(t, B) for t in b["trees"]) for b in Mo["bag"]], 0)
pick = (s >= Mo["threshold_top3"]) & (Z["guard"] == 1)
out = sys.argv[1].replace(".npz", f"_gdm_{nm}_picks.json"); json.dump([m for m, p in zip(M["mints"], pick) if p], open(out, "w"))
print(f"frozen {F['id']} sha {h[:12]} model {nm}: {pick.sum()} picks of {len(pick)} rows -> {out}")
