#!/usr/bin/env python3
"""9pQQ dissection, step 0: compact tape of EVERY landed pump.fun curve trade in a raw recording (all mints).
Read-only on the recordings; streams each 5-min gz file line by line.
Per file -> <OUT>/<run>/<file>.npz with
  a: int64 [n, 12] = s, i, bt, uid, mid, tok (signer token delta), sol (signer lamport delta, fees+tips incl.),
                     cpre, cpost (curve token balance), cup (CU price), tip (sum of tip transfers),
                     fl (bit0 pump curve program in tx, bit1 PumpSwap AMM program in tx)
  users: signer table, mints: mint table
usage: t0_tape.py OUT RUNDIR [RUNDIR ...]   (4 workers)"""
import sys, os, gzip, json
from multiprocessing import Pool
import numpy as np
CURVE = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
AMM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"

def job(a):
    src, dst = a
    if os.path.exists(dst): return -1
    U, M, rows = {}, {}, []
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
                for m in d.get("mints") or []:
                    tok, cur = 0, None
                    for mm, own, pre, post in tb:
                        if mm != m: continue
                        if own == sg: tok += (post or 0) - (pre or 0)
                        elif cur is None or (pre or 0) > cur[0]: cur = (pre or 0, post or 0)
                    if tok == 0 or cur is None: continue
                    rows.append((d["s"], d.get("i") or 0, d.get("bt") or 0, U.setdefault(sg, len(U)), M.setdefault(m, len(M)),
                                 tok, sol, cur[0], cur[1], d.get("cup") or 0, tip, fl))
        except (EOFError, OSError): pass
    a_ = np.array(rows, dtype=np.int64).reshape(-1, 12)
    np.savez(dst + ".tmp.npz", a=a_, users=np.array(list(U), dtype="U44"), mints=np.array(list(M), dtype="U44"))
    os.rename(dst + ".tmp.npz", dst)
    return len(rows)

if __name__ == "__main__":
    out = sys.argv[1]; jobs = []
    for rd in sys.argv[2:]:
        r = os.path.basename(rd.rstrip("/")); os.makedirs(f"{out}/{r}", exist_ok=True)
        for fn in sorted(os.listdir(f"{rd}/txs")):
            jobs.append((f"{rd}/txs/{fn}", f"{out}/{r}/{fn[:-9]}.npz"))
    tot = 0
    with Pool(4) as p:
        for k, n in enumerate(p.imap_unordered(job, jobs)):
            tot += max(n, 0)
            if k % 50 == 0: print(k, len(jobs), tot, flush=True)
    print("done", len(jobs), tot, flush=True)
