#!/usr/bin/env python3
# MODEL CHECK step 0c: m0_raw.py dropped the target wallets' own FAILED txs from the fail tables (progs was popped before the
# pump check). Re-extract them from raw/<run>/*.tx.jsonl.gz (all target txs): failed txs that name a non-WSOL mint, same compact
# format as *.fail.npz -> raw/<run>/<chunk>.tgfail.npz. (The pump-program test is replaced by the day-array token join in m3.)
import sys, os, json, gzip, glob, zlib
import numpy as np
from multiprocessing import Pool
OUT = "/home/moiz/sniper-data/modelcheck"; WSOL = "So11111111111111111111111111111111111111112"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m0_raw import code_of, kind_of
def work(f):
    rows = []
    try:
        for l in gzip.open(f, "rt"):
            if '"err":null' in l: continue
            r = json.loads(l); sg = r.get("signers") or []
            m = next((x for x in r.get("mints") or [] if x != WSOL), None)
            if not m or not sg: continue
            tips = sum(d for _, d in r.get("tips") or [])
            rows.append((r["s"], r["i"], zlib.crc32(sg[0].encode()), zlib.crc32(m.encode()), code_of(r.get("err")), kind_of(r.get("ixn")), r.get("fee") or 0, tips))
    except (EOFError, OSError, zlib.error): pass
    A = np.array(rows, np.int64).reshape(-1, 8)
    np.savez(f.replace(".tx.jsonl.gz", ".tgfail.npz"), s=A[:, 0], i=A[:, 1].astype(np.int32), payer=A[:, 2], mint=A[:, 3], code=A[:, 4].astype(np.int32),
             kind=A[:, 5].astype(np.int8), fee=A[:, 6], tips=A[:, 7])
    return len(rows)
if __name__ == "__main__":
    fs = sorted(glob.glob(f"{OUT}/raw/R*/*.tx.jsonl.gz")); tot = 0
    with Pool(5) as p:
        for k, n in enumerate(p.imap_unordered(work, fs, chunksize=4), 1):
            tot += n
            if k % 100 == 0: print(k, len(fs), tot, flush=True)
    print("DONE", tot, flush=True)
