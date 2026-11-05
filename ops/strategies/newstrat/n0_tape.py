#!/usr/bin/env python3
"""NEWSTRAT step 0: compact tape of every landed pump.fun trade (curve + PumpSwap) in a raw recording, all mints.
Read-only on recordings; streams each 5-min gz file. Same row logic as rivals/9pQQ/t0_tape.py, plus fee and a route id
(sorted set of 'extra' programs in the tx, e.g. terminals / routers / Lighthouse).
Per run -> /home/moiz/sniper-data/newstrat/tape/<run>.npz, rows sorted by (mint, s, i):
  s i bt u m tok sol cpre cpost cup tip fl rt fee     (fl bit0 curve program in tx, bit1 PumpSwap)
usage: n0_tape.py RUN [RUN ...]   (4 workers)"""
import sys, os, gzip, json
from multiprocessing import Pool
import numpy as np
COL = "/home/moiz/sniper-data/collect"
OUT = "/home/moiz/sniper-data/newstrat/tape"
CURVE = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
AMM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
BASE = {CURVE, AMM, "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", "11111111111111111111111111111111",
        "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL", "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ",
        "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "ComputeBudget111111111111111111111111111111",
        "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr", "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo"}

def job(src):
    U, M, R, rows = {}, {}, {}, []
    with gzip.open(src, "rt", errors="replace") as f:
        try:
            for l in f:
                if '"err":null' not in l: continue
                d = json.loads(l)
                tb = d.get("tb")
                if not tb: continue
                sg = (d.get("signers") or [None])[0]
                sd = d.get("sd") or []
                sol = next((v for a_, v in sd if a_ == sg), 0)
                tip = sum(v for _, v in (d.get("tips") or []))
                pg = d.get("progs") or []
                fl = (1 if CURVE in pg else 0) | (2 if AMM in pg else 0)
                if not fl: continue
                rt = R.setdefault(",".join(sorted(p for p in pg if p not in BASE)), len(R))
                for m in d.get("mints") or []:
                    tok, cur = 0, None
                    for mm, own, pre, post in tb:
                        if mm != m: continue
                        if own == sg: tok += (post or 0) - (pre or 0)
                        elif cur is None or (pre or 0) > cur[0]: cur = (pre or 0, post or 0)
                    if tok == 0 or cur is None: continue
                    rows.append((d["s"], d.get("i") or 0, d.get("bt") or 0, U.setdefault(sg, len(U)), M.setdefault(m, len(M)),
                                 tok, sol, cur[0], cur[1], d.get("cup") or 0, tip, fl, rt, d.get("fee") or 0))
        except (EOFError, OSError):
            pass
    a = np.array(rows, dtype=np.int64).reshape(-1, 14)
    return a, list(U), list(M), list(R)

def build(run):
    dst = f"{OUT}/{run}.npz"
    if os.path.exists(dst): print("exists", dst); return
    files = sorted(f"{COL}/{run}/txs/{fn}" for fn in os.listdir(f"{COL}/{run}/txs") if fn.endswith(".jsonl.gz"))
    UG, MG, RG = {}, {}, {}
    parts = []
    with Pool(4) as p:
        for k, (a, us, ms, rs) in enumerate(p.imap(job, files, chunksize=2)):
            if len(a):
                um = np.array([UG.setdefault(x, len(UG)) for x in us], np.int64)
                mm = np.array([MG.setdefault(x, len(MG)) for x in ms], np.int64)
                rm = np.array([RG.setdefault(x, len(RG)) for x in rs], np.int64)
                a[:, 3] = um[a[:, 3]]; a[:, 4] = mm[a[:, 4]]; a[:, 12] = rm[a[:, 12]]
                parts.append(a)
            if k % 40 == 0: print(run, k, len(files), sum(len(x) for x in parts), flush=True)
    a = np.concatenate(parts)
    del parts
    o = np.lexsort((a[:, 1], a[:, 0], a[:, 4]))
    a = a[o]
    nm = len(MG)
    mstart = np.searchsorted(a[:, 4], np.arange(nm + 1))
    np.savez(dst + ".tmp.npz", s=a[:, 0], i=a[:, 1].astype(np.int32), bt=a[:, 2], u=a[:, 3].astype(np.int32),
             m=a[:, 4].astype(np.int32), tok=a[:, 5], sol=a[:, 6], cpre=a[:, 7], cpost=a[:, 8], cup=a[:, 9], tip=a[:, 10],
             fl=a[:, 11].astype(np.int8), rt=a[:, 12].astype(np.int32), fee=a[:, 13], mstart=mstart,
             users=np.array(list(UG), dtype="U44"), mints=np.array(list(MG), dtype="U44"), routes=np.array(list(RG)))
    os.rename(dst + ".tmp.npz", dst)
    print("done", run, len(a), flush=True)

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for r in sys.argv[1:]: build(r)
