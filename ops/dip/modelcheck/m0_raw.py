#!/usr/bin/env python3
# MODEL CHECK step 0 (read-only, local recording only): one pass over the raw collector chunks of R1..R4.
#  (a) every tx signed by a target wallet (targets.txt: fast dip backrunners + census >=100-trip wallets), success AND failed,
#      full record minus progs -> raw/<run>/<chunk>.tx.jsonl.gz   (exact fee, tips, SOL deltas for real P&L)
#  (b) every FAILED tx that touches the pump.fun bonding-curve program (any signer), compact -> raw/<run>/<chunk>.fail.npz
#      columns: s, i, payer crc32, mint crc32 (first non-WSOL mint), err code (Custom n, else -1), kind (1 buy ixn, 2 sell ixn,
#      0 unknown e.g. routed), fee, tips.  (used for follower tolerance: who failed right after a dump, at what price)
# usage: nice python3 -I m0_raw.py [procs]
import sys, os, json, gzip, glob, zlib
import numpy as np
from multiprocessing import Pool
D = "/home/moiz/sniper-data/collect"; OUT = "/home/moiz/sniper-data/modelcheck/raw"
RUNS = {"R1": "run_20261021_2207", "R2": "run_20261022_1543", "R3": "run_20261023_1426", "R4": "run_20261024_1425"}
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"; WSOL = "So11111111111111111111111111111111111111112"
HERE = os.path.dirname(os.path.abspath(__file__))
W = [l.strip() for l in open(os.path.join(HERE, "targets.txt")) if l.strip()]
WS = set(W)
def code_of(e):
    try:
        ie = e.get("InstructionError")
        if ie and isinstance(ie[1], dict) and "Custom" in ie[1]: return int(ie[1]["Custom"])
    except Exception: pass
    return -1
def kind_of(ixn):
    k = 0
    for x in ixn or []:
        if x.startswith("Buy"): return 1
        if x.startswith("Sell"): k = 2
    return k
def work(a):
    tag, path = a
    base = os.path.basename(path).split(".")[0]; od = os.path.join(OUT, tag)
    fo = os.path.join(od, base + ".fail.npz")
    if os.path.exists(fo): return tag, base, -1, 0, 0
    rows = []; ntx = 0; nt = 0
    tf = gzip.open(os.path.join(od, base + ".tx.jsonl.gz.tmp"), "wt", compresslevel=3)
    try:
        for line in gzip.open(path, "rt"):
            ntx += 1
            hasp = PUMP in line; ok = '"err":null' in line
            a = line.find('"signers":['); tw = False
            if a >= 0:
                b = line.find("]", a); sgs = line[a + 11:b].replace('"', "").split(",")
                tw = any(x in WS for x in sgs)
            if not tw and (not hasp or ok): continue
            try: r = json.loads(line)
            except Exception: continue
            sg = r.get("signers") or []
            if tw and WS.intersection(sg):
                r.pop("progs", None); tf.write(json.dumps(r, separators=(",", ":")) + "\n"); nt += 1
            if hasp and not ok and PUMP in (r.get("progs") or []):
                m = next((x for x in r.get("mints") or [] if x != WSOL), None)
                tips = sum(d for _, d in r.get("tips") or [])
                rows.append((r["s"], r["i"], zlib.crc32(sg[0].encode()) if sg else 0, zlib.crc32(m.encode()) if m else 0, code_of(r.get("err")),
                             kind_of(r.get("ixn")), r.get("fee") or 0, tips))
    except (EOFError, OSError, zlib.error): pass
    tf.close(); os.replace(os.path.join(od, base + ".tx.jsonl.gz.tmp"), os.path.join(od, base + ".tx.jsonl.gz"))
    A = np.array(rows, np.int64).reshape(-1, 8)
    np.savez(fo + ".tmp.npz", s=A[:, 0], i=A[:, 1].astype(np.int32), payer=A[:, 2], mint=A[:, 3], code=A[:, 4].astype(np.int32),
             kind=A[:, 5].astype(np.int8), fee=A[:, 6], tips=A[:, 7])
    os.replace(fo + ".tmp.npz", fo)
    return tag, base, ntx, nt, len(rows)
if __name__ == "__main__":
    P = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    jobs = []
    for t, r in RUNS.items():
        os.makedirs(os.path.join(OUT, t), exist_ok=True)
        jobs += [(t, f) for f in sorted(glob.glob(f"{D}/{r}/txs/*.jsonl.gz"))]
    tot = [0, 0, 0]
    with Pool(P) as p:
        for k, (tag, base, n, nt, nf) in enumerate(p.imap_unordered(work, jobs), 1):
            if n > 0: tot[0] += n; tot[1] += nt; tot[2] += nf
            if k % 25 == 0 or k == len(jobs): print(f"{k}/{len(jobs)} chunks | txs {tot[0]} | target txs {tot[1]} | failed pump txs {tot[2]}", flush=True)
    print("DONE", tot, flush=True)
