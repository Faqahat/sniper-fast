#!/usr/bin/env python3
# MODEL CHECK step 0b: compact table of every target-wallet tx (raw/<run>/*.tx.jsonl.gz from m0_raw.py):
# s, i, signer crc32 (first target signer), ok, fee, tips, wallet SOL delta (sd), number of pump trade events, err code
# -> /home/moiz/sniper-data/modelcheck/txc_<run>.npz         usage: nice python3 -I m0b_txcost.py [procs]
import sys, os, json, gzip, glob, zlib
import numpy as np
from multiprocessing import Pool
OUT = "/home/moiz/sniper-data/modelcheck"; HERE = os.path.dirname(os.path.abspath(__file__))
W = [l.strip() for l in open(os.path.join(HERE, "targets.txt")) if l.strip()]; WS = set(W)
def code_of(e):
    if e is None: return 0
    try:
        ie = e.get("InstructionError")
        if ie and isinstance(ie[1], dict) and "Custom" in ie[1]: return int(ie[1]["Custom"])
    except Exception: pass
    return -1
def work(f):
    rows = []
    try:
        for l in gzip.open(f, "rt"):
            r = json.loads(l)
            sg = [x for x in r.get("signers") or [] if x in WS]
            if not sg: continue
            w = sg[0]
            sd = next((dlt for k, dlt in r.get("sd") or [] if k == w), 0)
            tips = sum(dlt for _, dlt in r.get("tips") or [])
            rows.append((r["s"], r["i"], zlib.crc32(w.encode()), 1 if r.get("err") is None else 0, r.get("fee") or 0, tips, sd, len(r.get("ev") or []), code_of(r.get("err")),
                         1 if (r.get("signers") or [None])[0] == w else 0))
    except (EOFError, OSError, zlib.error): pass
    return rows
if __name__ == "__main__":
    P = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    for run in ("R1", "R2", "R3", "R4"):
        fs = sorted(glob.glob(f"{OUT}/raw/{run}/*.tx.jsonl.gz")); R = []
        with Pool(P) as p:
            for rows in p.imap_unordered(work, fs, chunksize=4): R += rows
        A = np.array(R, np.int64).reshape(-1, 10)
        o = np.lexsort((A[:, 1], A[:, 0])); A = A[o]
        np.savez(f"{OUT}/txc_{run}.npz", s=A[:, 0], i=A[:, 1].astype(np.int32), w=A[:, 2], ok=A[:, 3].astype(np.int8), fee=A[:, 4], tips=A[:, 5], sd=A[:, 6],
                 nev=A[:, 7].astype(np.int16), code=A[:, 8].astype(np.int32), payer=A[:, 9].astype(np.int8))
        print(run, len(A), "txs", flush=True)
