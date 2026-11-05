#!/usr/bin/env python3
"""FLATPERFECT step 4 [MEASURED, read-only on raw recordings]: extend the flatsig chain with recording chunks it does not have yet
(same decoder: flatsig f1_extract.job), then merge everything (flatsig raw + ours) like flatsig f3_chain.py into
/home/moiz/sniper-data/flatperfect/chain/{chain.npz, fails.npz, spans.json}.
usage: fp4_chain_extend.py COLLECT_RUNDIR [COLLECT_RUNDIR ...]"""
import sys, os, glob, json, time, collections
import numpy as np
from multiprocessing import Pool
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/flatsig")
import f1_extract as F1
FSRAW = "/home/moiz/sniper-data/flatsig/raw"
MYRAW = "/home/moiz/sniper-data/flatperfect/raw"
OUT = "/home/moiz/sniper-data/flatperfect/chain"
if __name__ == "__main__":
    jobs = []
    for rd in sys.argv[1:]:
        r = os.path.basename(rd.rstrip("/")); os.makedirs(f"{MYRAW}/{r}", exist_ok=True)
        for fn in sorted(os.listdir(f"{rd}/txs")):
            if not fn.endswith(".gz") or os.path.getmtime(f"{rd}/txs/{fn}") > time.time() - 240: continue
            base = fn[:-9]
            if os.path.exists(f"{FSRAW}/{r}/{base}.npz"): continue
            jobs.append((f"{rd}/txs/{fn}", f"{MYRAW}/{r}/{base}.npz"))
    print("new chunks", len(jobs), flush=True)
    with Pool(10) as p:
        for d, a, b in p.imap_unordered(F1.job, jobs): print(os.path.basename(d), a, b, flush=True)
    T = collections.defaultdict(list); F = collections.defaultdict(list); spans = []
    runs = sorted(set(os.path.basename(x) for x in glob.glob(f"{FSRAW}/run_*") + glob.glob(f"{MYRAW}/run_*")))
    for run in runs:
        lo, hi = 1 << 62, 0
        for pth in sorted(glob.glob(f"{FSRAW}/{run}/*.npz") + glob.glob(f"{MYRAW}/{run}/*.npz")):
            z = np.load(pth)
            if len(z["t_slot"]): lo = min(lo, int(z["t_slot"].min())); hi = max(hi, int(z["t_slot"].max()))
            for k in z.files: (T if k.startswith("t_") else F)[k[2:]].append(z[k])
        spans.append([run, lo, hi])
    T = {k: np.concatenate(v) for k, v in T.items()}; F = {k: np.concatenate(v) for k, v in F.items()}
    key = T["slot"].astype(np.int64) * (1 << 20) + T["idx"].astype(np.int64) * 64 + T["j"].astype(np.int64)
    _, u = np.unique(key, return_index=True); T = {k: v[u] for k, v in T.items()}
    o = np.lexsort((T["j"], T["idx"], T["slot"], T["mint"])); T = {k: v[o] for k, v in T.items()}
    keyf = F["slot"].astype(np.int64) * (1 << 20) + F["idx"].astype(np.int64)
    _, u = np.unique(keyf, return_index=True); F = {k: v[u] for k, v in F.items()}
    o = np.lexsort((F["idx"], F["slot"], F["mint"])); F = {k: v[o] for k, v in F.items()}
    os.makedirs(OUT, exist_ok=True)
    np.savez(f"{OUT}/chain.npz", **T); np.savez(f"{OUT}/fails.npz", **F); json.dump(spans, open(f"{OUT}/spans.json", "w"))
    print("trades", len(T["slot"]), "fails", len(F["slot"]), spans, flush=True)
