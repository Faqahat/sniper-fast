#!/usr/bin/env python3
"""PRESEND FILTER, step 2b: the failed txs of the mints of interest (g1 chunks) -> fails.npz, chain order, recording overlaps removed.
Interned with ids.json (extended in place: new wallets / mints appended). The signature is kept only for OUR wallets' failed txs
(the tries the engine logged as unseen). Columns: s, i, bt, signer, mint, err (id into ids['e']), fee, cup, cul, prog, sig (ours only)."""
import glob, json, os, time
import numpy as np
B = "/home/moiz/sniper-data/presend_filter"
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
t0 = time.time()
I = json.load(open(f"{B}/ids.json"))
ids = {k: {s: n for n, s in enumerate(v)} for k, v in I.items()}
ids.setdefault("e", {})
def intern(tab, arr):
    d = ids[tab]; out = np.empty(len(arr), np.uint32)
    for k, s in enumerate(arr.tolist()):
        v = d.get(s)
        if v is None: v = d[s] = len(d)
        out[k] = v
    return out
cols = {c: [] for c in ("s", "i", "bt", "fee", "cup", "cul", "signer", "mint", "err", "prog")}; ours = {}
files = sorted(glob.glob(f"{B}/g1/*.npz"), key=lambda f: int(os.path.basename(f).split("__txs_")[1][:10]))
for k, f in enumerate(files):
    z = np.load(f)
    if "f_s" not in z: continue
    for c in ("s", "i", "bt", "fee", "cup", "cul"): cols[c].append(z["f_" + c])
    sg = z["f_signer"]
    cols["signer"].append(intern("w", sg)); cols["mint"].append(intern("m", z["f_mint"])); cols["err"].append(intern("e", z["f_err"])); cols["prog"].append(intern("p", z["f_prog"]))
    m = np.isin(sg, list(OURS))
    for sig, s, i, fee in zip(z["f_sig"][m].tolist(), z["f_s"][m].tolist(), z["f_i"][m].tolist(), z["f_fee"][m].tolist()): ours[sig] = (s, i, fee)
    if k % 100 == 0: print(k, f"{time.time() - t0:.0f}s", flush=True)
F = {c: np.concatenate(v) for c, v in cols.items()}
o = np.lexsort((F["i"], F["s"])); F = {c: v[o] for c, v in F.items()}
fd = np.zeros(len(F["s"]), bool); fd[1:] = (F["s"][1:] == F["s"][:-1]) & (F["i"][1:] == F["i"][:-1])
F = {c: v[~fd] for c, v in F.items()}
np.savez(f"{B}/fails.npz", **F)
json.dump({k: list(d.keys()) for k, d in ids.items()}, open(f"{B}/ids.json", "w"))
json.dump(ours, open(f"{B}/our_fails.json", "w"))
print(f"fails {len(F['s']):,} (dups {int(fd.sum()):,}), ours {len(ours):,}, {time.time() - t0:.0f}s")
