#!/usr/bin/env python3
"""grad agent, step 2: reduce the per-chunk decode (g1) into one compact tape.
Out (in /home/moiz/sniper-data/e2x1_dissect/grad/):
  tape.npz : tr (curve trades, vsol>=45 SOL, mints whose max vsol >= 75 SOL; sorted mint, slot, idx, j; dedup by tx+event)
             ps (PumpSwap events of migrated pools, migration slot .. +12000 slots; sorted pool, slot, idx, j)
             slots (slot, bt, maxi) union over chunks
  meta.pkl : mints, pools, users (id -> string), mig (list), cmp (dict mint -> first complete), cr (dict mint -> create), mx (mint -> max vsol)
"""
import glob, json, os, pickle, sys
import numpy as np

DEC = "/home/moiz/sniper-data/e2x1_dissect/grad/dec"
OUT = "/home/moiz/sniper-data/e2x1_dissect/grad"
files = sorted(glob.glob(DEC + "/*.npz"), key=lambda f: (os.path.basename(f).split("__")[0], os.path.basename(f).split("__")[1]))
print(len(files), "chunks", flush=True)

# pass 1: migrations, completes, creates, max vsol, slots
mig = {}; cmp_ = {}; cr = {}; mx = {}; slots = {}
for f in files:
    z = np.load(f, allow_pickle=True)
    for x in z["mig"]:
        d = json.loads(x); mig.setdefault(d["sig"], d)
    for x in z["cmp"]:
        d = json.loads(x)
        if d["mint"] not in cmp_ or d["slot"] < cmp_[d["mint"]]["slot"]: cmp_[d["mint"]] = d
    for x in z["cr"]:
        d = json.loads(x); cr.setdefault(d["mint"], d)
    for k, v in json.loads(z["mx"][0]).items():
        if v > mx.get(k, 0): mx[k] = v
    for s, bt, mi in z["slots"]:
        o = slots.get(int(s))
        if o is None or mi > o[1]: slots[int(s)] = (int(bt), int(mi))
mig = sorted(mig.values(), key=lambda d: (d["slot"], d["idx"]))
pool_win = {}
for d in mig:
    if d["pool"] not in pool_win: pool_win[d["pool"]] = (d["slot"], d["slot"] + 12000)
near = {m for m, v in mx.items() if v >= 75_000_000_000}
print("mig", len(mig), "cmp", len(cmp_), "creates", len(cr), "mints", len(mx), "near75", len(near), "slots", len(slots), flush=True)

# pass 2: trades + pool events
gm, gml = {}, []
def gid(k, d=gm, l=gml):
    v = d.get(k)
    if v is None: v = d[k] = len(l); l.append(k)
    return v
gp, gpl = {}, []; gu, gul = {}, []
TR, PS = [], []
for n, f in enumerate(files):
    z = np.load(f, allow_pickle=True); ids = z["ids"]
    tr = z["tr"]
    if len(tr):
        names = ids[tr["mint"]]
        keep = np.array([m in near for m in names])
        tr = tr[keep]
        if len(tr):
            t2 = tr.copy()
            t2["mint"] = [gid(m) for m in ids[tr["mint"]]]
            t2["user"] = [gid(u, gu, gul) for u in ids[tr["user"]]]
            t2["signer"] = [gid(u, gu, gul) for u in ids[tr["signer"]]]
            TR.append(t2)
    ps = z["ps"]
    if len(ps):
        pn = ids[ps["pool"]]
        keep = np.array([(p in pool_win) and (pool_win[p][0] <= s <= pool_win[p][1]) for p, s in zip(pn, ps["slot"])])
        ps = ps[keep]
        if len(ps):
            p2 = ps.copy()
            p2["pool"] = [gid(p, gp, gpl) for p in ids[ps["pool"]]]
            p2["user"] = [gid(u, gu, gul) for u in ids[ps["user"]]]
            p2["signer"] = [gid(u, gu, gul) for u in ids[ps["signer"]]]
            p2["txmint"] = [gid(m) for m in ids[ps["txmint"]]]
            PS.append(p2)
    if n % 200 == 0: print(n, sum(len(x) for x in TR), sum(len(x) for x in PS), flush=True)
TR = np.concatenate(TR); PS = np.concatenate(PS)
# dedup (same tx recorded by two overlapping runs)
def dedup(a):
    k = a["sigh"].astype(np.uint64) ^ (a["j"].astype(np.uint64) << np.uint64(56))
    _, u = np.unique(k, return_index=True)
    return a[np.sort(u)]
n0, p0 = len(TR), len(PS)
TR = dedup(TR); PS = dedup(PS)
TR = TR[np.lexsort((TR["j"], TR["idx"], TR["slot"], TR["mint"]))]
PS = PS[np.lexsort((PS["j"], PS["idx"], PS["slot"], PS["pool"]))]
print("TR", n0, "->", len(TR), "PS", p0, "->", len(PS), flush=True)
sl = np.array([(k, v[0], v[1]) for k, v in sorted(slots.items())], dtype=np.uint64)
np.savez(OUT + "/tape.npz", tr=TR, ps=PS, slots=sl)
pickle.dump(dict(mints=gml, pools=gpl, users=gul, mig=mig, cmp=cmp_, cr=cr, mx=mx), open(OUT + "/meta.pkl", "wb"))
print("saved", flush=True)
