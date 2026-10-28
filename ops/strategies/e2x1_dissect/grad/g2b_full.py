#!/usr/bin/env python3
"""grad agent, step 2b: replace the tape's curve trades (vsol>=45 only) with FULL-depth curve trades of every non-mayhem mint that
reached 78 vSOL (from the KEEP-mode decode in decfull/). Needed so stop-losses / timeouts see crashes below 45 vSOL."""
import glob, os, pickle
import numpy as np
G = "/home/moiz/sniper-data/e2x1_dissect/grad"
M = pickle.load(open(G + "/meta.pkl", "rb")); Z = np.load(G + "/tape.npz")
keep = {m for m, v in M["mx"].items() if v >= 78e9 and m in M["cr"] and not M["cr"][m].get("mayhem")}
gm = {m: k for k, m in enumerate(M["mints"])}; gml = list(M["mints"])
gu = {u: k for k, u in enumerate(M["users"])}; gul = list(M["users"])
def gid(k, d, l):
    v = d.get(k)
    if v is None: v = d[k] = len(l); l.append(k)
    return v
files = sorted(glob.glob(G + "/decfull/*.npz"))
TR = []
for n, f in enumerate(files):
    z = np.load(f, allow_pickle=True); ids = z["ids"]; tr = z["tr"]
    if not len(tr): continue
    names = ids[tr["mint"]]; tr = tr[np.array([m in keep for m in names])]
    if not len(tr): continue
    t2 = tr.copy()
    t2["mint"] = [gid(m, gm, gml) for m in ids[tr["mint"]]]
    t2["user"] = [gid(u, gu, gul) for u in ids[tr["user"]]]
    t2["signer"] = [gid(u, gu, gul) for u in ids[tr["signer"]]]
    TR.append(t2)
    if n % 300 == 0: print(n, sum(len(x) for x in TR), flush=True)
TR = np.concatenate(TR)
k = TR["sigh"].astype(np.uint64) ^ (TR["j"].astype(np.uint64) << np.uint64(56)); _, u = np.unique(k, return_index=True); TR = TR[np.sort(u)]
TR = TR[np.lexsort((TR["j"], TR["idx"], TR["slot"], TR["mint"]))]
print("full TR", len(TR), "mints", len(np.unique(TR["mint"])), flush=True)
np.savez(G + "/tape.npz.new.npz", tr=TR, ps=Z["ps"], slots=Z["slots"])
os.replace(G + "/tape.npz.new.npz", G + "/tape.npz")
M["mints"] = gml; M["users"] = gul
pickle.dump(M, open(G + "/meta.pkl.new", "wb")); os.replace(G + "/meta.pkl.new", G + "/meta.pkl")
print("saved", flush=True)
