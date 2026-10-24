#!/usr/bin/env python3
# read-only: pull every raw tx (success AND failed) signed by any wallet in a list, from all raw chunks of both runs.
# usage: raw_extract.py <wallets.txt> <outdir> [procs]
import os, sys, gzip, glob, zlib, json
from multiprocessing import Pool
D = "/home/moiz/sniper-data/collect"
WL = set(l.strip() for l in open(sys.argv[1]) if l.strip()); OUT = sys.argv[2]
PROCS = int(sys.argv[3]) if len(sys.argv) > 3 else 4
WLB = {w.encode() for w in WL}
def work(path):
    run = path.split("/")[-3]; tag = os.path.basename(path).split(".")[0]
    of = os.path.join(OUT, f"{run}__{tag}.jsonl.gz")
    if os.path.exists(of): return path, -1
    n = 0; m = 0; tmp = of + ".tmp"
    with gzip.open(tmp, "wb", compresslevel=3) as fo:
        try:
            with gzip.open(path, "rb") as fi:
                for line in fi:
                    n += 1
                    k = line.find(b'"signers":[')
                    if k < 0: continue
                    e = line.find(b']', k)
                    for x in line[k + 11:e].split(b','):
                        if x.strip(b' "') in WLB:
                            fo.write(line if line.endswith(b"\n") else line + b"\n"); m += 1; break
        except (EOFError, OSError, zlib.error): pass
    os.rename(tmp, of)
    return path, m
if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    files = sorted(glob.glob(os.path.join(D, "run_20261022_1543", "txs", "*.jsonl.gz"))) + sorted(glob.glob(os.path.join(D, "run_20261023_1426", "txs", "*.jsonl.gz")))
    # skip the newest chunk of the live run (may still be written)
    live = sorted(glob.glob(os.path.join(D, "run_20261023_1426", "txs", "*.jsonl.gz")))
    if live: files = [f for f in files if f != live[-1]]
    tot = 0
    with Pool(PROCS) as p:
        for k, (path, m) in enumerate(p.imap_unordered(work, files), 1):
            tot += max(m, 0)
            if k % 20 == 0: print(k, len(files), tot, flush=True)
    print("DONE", tot, flush=True)
