#!/usr/bin/env python3
"""FLATSIG step 3 [MEASURED]: merge the f1 chunk arrays into one chain table, de-duplicated across overlapping recordings,
sorted by (mint, slot, idx, j); failed bot-attempt rows likewise. Also the recorded slot spans (gaps between recordings are listed).
Out: /home/it/sniper-data/flatsig/chain.npz, fails.npz, spans.json"""
import numpy as np, json, glob, os, collections
D = "/home/it/sniper-data/flatsig"
T = collections.defaultdict(list); F = collections.defaultdict(list); spans = []
for run in sorted(glob.glob(f"{D}/raw/run_*")):
    lo, hi = 1 << 62, 0
    for p in sorted(glob.glob(f"{run}/*.npz")):
        z = np.load(p)
        if len(z["t_slot"]):
            lo = min(lo, int(z["t_slot"].min())); hi = max(hi, int(z["t_slot"].max()))
        for k in z.files:
            (T if k.startswith("t_") else F)[k[2:]].append(z[k])
    spans.append([os.path.basename(run), lo, hi])
T = {k: np.concatenate(v) for k, v in T.items()}
F = {k: np.concatenate(v) for k, v in F.items()}
# de-dup trades on (slot, idx, j)
key = T["slot"].astype(np.int64) * (1 << 20) + T["idx"].astype(np.int64) * 64 + T["j"].astype(np.int64)
_, u = np.unique(key, return_index=True)
T = {k: v[u] for k, v in T.items()}
o = np.lexsort((T["j"], T["idx"], T["slot"], T["mint"]))
T = {k: v[o] for k, v in T.items()}
keyf = F["slot"].astype(np.int64) * (1 << 20) + F["idx"].astype(np.int64)
_, u = np.unique(keyf, return_index=True)
F = {k: v[u] for k, v in F.items()}
o = np.lexsort((F["idx"], F["slot"], F["mint"]))
F = {k: v[o] for k, v in F.items()}
np.savez(f"{D}/chain.npz", **T)
np.savez(f"{D}/fails.npz", **F)
json.dump(spans, open(f"{D}/spans.json", "w"))
print("trades", len(T["slot"]), "fails", len(F["slot"]), "mints", len(np.unique(T["mint"])), spans)
