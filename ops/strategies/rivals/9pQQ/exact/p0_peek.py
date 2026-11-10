import gzip, json, glob, collections, numpy as np, sys
import xlib as X
r = "run_20261030_1355"; t = X.load(r)
trig = set(zip(t.s[t.ob_trig[t.ob_trig >= 0]].tolist(), t.i[t.ob_trig[t.ob_trig >= 0]].tolist()))
flat_oth = np.where(~t.own & ~t.hold & ~t.trig_b)[0]
rng = np.random.default_rng(0); samp = set(zip(t.s[flat_oth].tolist(), t.i[flat_oth].tolist()))
files = sorted(glob.glob(f"/data/tapes/collect/{r}/txs/*.gz"))[100:130]
A = collections.Counter(); B = collections.Counter(); nA = nB = 0
def sig(d):
    pg = tuple(sorted(p[:6] for p in d.get("progs") or []))
    tips = len(d.get("tips") or [])
    return pg, tips, d.get("ixn")[-1] if d.get("ixn") else None
for fn in files:
    for l in gzip.open(fn, "rt"):
        d = json.loads(l); k = (d["s"], d.get("i") or 0)
        if k in trig: A[sig(d)] += 1; nA += 1
        elif k in samp and rng.random() < 0.2: B[sig(d)] += 1; nB += 1
print("trig", nA, "others", nB)
keys = set(k for k, v in A.most_common(25)) | set(k for k, v in B.most_common(25))
rows = sorted(keys, key=lambda k: -(A[k] / max(nA, 1) + B[k] / max(nB, 1)))
for k in rows[:40]: print(f"{A[k]/nA:.3f} {B[k]/nB:.3f} lift {(A[k]/nA)/max(B[k]/nB,1e-4):6.2f}  {k}")
