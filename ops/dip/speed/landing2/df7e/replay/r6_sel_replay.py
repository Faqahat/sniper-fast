#!/usr/bin/env python3
# DF7e replay step 6: replay of his SELECTION written as explicit rules (tree leaves fit on his first half, r5_select.py), and of
# copying his landed buys, at our execution. 0.5 SOL, +5% guard, main exit (trail 9/10%/5 quiet). Read-only, 5 workers.
#   SEL-A: dump drop > 9.5%, ntr150 > 19 (active token: > 19 trades in the last 150 slots), flow5 > -4.73 SOL     (his take 12%)
#   SEL-B: SEL-A + (drop > 9.5%, ntr150 5..19) + (drop 5.2..9.5%, ntr150 > 16)                                     (take >= 3.5%)
#   COPY : trigger = his own landed buy (we see it on our feed and buy after it)
import sys, os, json, time, numpy as np
from multiprocessing import Pool
import r3_replay as R3
import rlib, sim2
D = R3.D; T = D.T
Z = np.load(rlib.DD + "/sel.npz"); idx = Z["idx"]; sc = Z["score"]
SEL = {"A": idx[sc >= 0.10], "B": idx[sc >= 0.03]}
uid = D.users.index(rlib.W)
COPY = np.where((T["user"] == uid) & (T["buy"] == 1))[0]
def null_for(cand, seed):
    rng = np.random.default_rng(2000 + seed); out = []
    hc = np.bincount(R3.hb[cand], minlength=R3.hb.max() + 1); he = R3.hb[R3.env]
    for h in range(len(hc)):
        p = R3.env[he == h]
        if hc[h] and len(p): out.append(rng.choice(p, min(hc[h], len(p)), replace=False))
    return np.concatenate(out)
def job(a):
    name, ck, land, mo, S, seed = a
    fn = f"{R3.OUT}/{name}_s{seed}.npy"
    if os.path.exists(fn): return name, seed, "cached"
    t0 = time.time()
    cand = SEL[ck[4:]] if ck.startswith("sel_") else COPY if ck == "copy" else null_for(SEL[ck[5:]], seed)
    S_ = sim2.Sim(D, S=S, guard=1.05, exit=R3.EXITS["trail"], holds=R3.HOLDS, land=R3.LAND[land], max_open=mo, seed=seed)
    rows = S_.run(cand)
    ci = cand[rows[:, 0].astype(np.int64)]
    extra = np.stack([R3.cls[ci].astype(np.float64), T["slot"][ci].astype(np.float64), ci.astype(np.float64)], 1)
    np.save(fn, np.concatenate([rows, extra], 1))
    return name, seed, f"{len(rows)} rows {time.time() - t0:.0f}s"
JOBS = []
for mo in (1, 3, 99):
    for ck in ("A", "B"):
        for land in ("ours", "ours-25ms", "ours-35ms"):
            JOBS += [(f"sel{ck}_{land}_m{mo}", f"sel_{ck}", land, mo, 0.5, s) for s in range(5)]
        JOBS += [(f"nullsel{ck}_ours_m{mo}", f"null_{ck}", "ours", mo, 0.5, s) for s in range(5)]
for land in ("ours", "ours-25ms", "ours-35ms"):
    JOBS += [(f"copy_{land}_m99", "copy", land, 99, 0.5, s) for s in range(5)]
if __name__ == "__main__":
    print({k: len(v) for k, v in SEL.items()}, "copy", len(COPY), flush=True)
    with Pool(5) as p:
        for r in p.imap_unordered(job, JOBS): print(*r, flush=True)
    print("DONE")
