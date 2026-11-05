#!/usr/bin/env python3
"""APEX2 check: per-mint old APEX sim (D7) vs new APEX2 sim, same launches; old P (18 ms) vs new P18/A/M/E, 0.4 SOL, h2."""
import pickle, glob, numpy as np, collections
old = {}
for d in ("D7", "TEST8"):
    for r in pickle.load(open(f"/home/moiz/sniper-data/apexsnipe/sim_{d}.pkl", "rb")): old.setdefault(r[0], r)
new = {}
for f in glob.glob("/home/moiz/sniper-data/apex2/res/run_*.pkl"):
    for r in pickle.load(open(f, "rb")): new.setdefault(r[0], r)
both = [m for m in old if m in new]
print("old D7 launches", len(old), "in new (serial creators only)", len(both))
o = np.array([old[m][8][1, 1, 0, 0] for m in both])
for pi, p in enumerate(("P18", "A", "R1", "R2", "M", "E", "N")):
    n = np.array([new[m][6][pi, 2, 0, 0] for m in both]); ok = np.isfinite(o) & np.isfinite(n)
    d = n[ok] - o[ok]
    print(f"{p}: both-ok {ok.sum()}  old mean {o[ok].mean()*1e3:+.2f} mSOL  new mean {n[ok].mean()*1e3:+.2f}  |diff|<0.1mSOL {np.mean(np.abs(d)<1e-4):.2f}  corr {np.corrcoef(o[ok], n[ok])[0,1]:.3f}")
# where old P sat vs new structure
k = collections.Counter()
for m in both:
    info = new[m][5]; oA = old[m][9][1]
    k[(info["pos_k"]["P18"] == info["pos_k"]["A"], info["ncs"] > 0)] += 1
print("P18==A, has create-slot snipers:", k)
