#!/usr/bin/env python3
"""FRONT step 2a (read-only): list the raw-recording lines we need (by '{"s":SLOT,"i":IDX,' prefix), one pattern file per raw chunk.
Targets: on the paying set S (front buyer 1 lands in the dump's slot and a 0.40 SOL buy just before it is worth >= +30 mSOL, wave)
the dump tx and the first 6 buy txs after it; on a CONTROL sample of 8,000 crowded non-paying dumps (front buyer 1 same slot,
front value < 0 or not valued) the dump tx and the first 3 buys.
Out: scratch hd_front/pat/<run>__<chunk>.pat, sniper-data/haqq_dissect/front/f2_sets.pkl (indices of S and control in f1.pkl)"""
import pickle, json, os, collections
import numpy as np
OUT = "/home/moiz/sniper-data/haqq_dissect/front"
SCR = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/hd_front/pat"
os.makedirs(SCR, exist_ok=True)
R = pickle.load(open(f"{OUT}/f1.pkl", "rb"))
S = [i for i, r in enumerate(R) if r["front"] and r["front"][0]["dsl"] == 0 and (r["front"][0].get("vpos") or -1) >= 0.030]
C0 = [i for i, r in enumerate(R) if r["front"] and r["front"][0]["dsl"] == 0 and (np.isnan(r["vf"]) or r["vf"] < 0)]
rng = np.random.default_rng(3); C = sorted(rng.choice(C0, 8000, replace=False).tolist())
pickle.dump(dict(S=S, C=C), open(f"{OUT}/f2_sets.pkl", "wb"))
tg = set()
for i in S:
    r = R[i]; tg.add((r["ds"], r["di"]))
    for f in r["front"][:6]: tg.add((f["slot"], f["idx"]))
for i in C:
    r = R[i]; tg.add((r["ds"], r["di"]))
    for f in r["front"][:3]: tg.add((f["slot"], f["idx"]))
F = json.load(open("/home/moiz/sniper-data/dv8/tab/files.json"))
F = [f for f in F if f["slot_hi"] >= 460541261 - 100]
lo = np.array([f["slot_lo"] for f in F]); hi = np.array([f["slot_hi"] for f in F])
o = np.argsort(lo); F = [F[k] for k in o]; lo = lo[o]; hi = hi[o]
per = collections.defaultdict(list); miss = 0
for s, i in tg:
    k = int(np.searchsorted(lo, s, side="right")) - 1
    if k < 0 or s > hi[k]: miss += 1; continue
    per[F[k]["npz"][:-4]].append(f'{{"s":{s},"i":{i},')
for name, v in per.items():
    open(f"{SCR}/{name}.pat", "w").write("\n".join(sorted(set(v))) + "\n")
print(f"S {len(S):,} control {len(C):,}; targets {len(tg):,} in {len(per)} chunks; not in any chunk {miss}")
