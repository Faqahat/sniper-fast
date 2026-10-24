#!/usr/bin/env python3
# For a set of tx signatures, pull the collector's raw row fields (progs = every program the tx invoked, ixn, signers) from
# the raw 5-min chunks (txs/*.jsonl.gz of both runs). Local files only. Parallel over chunks.
# usage: python3 -I scan_progs.py sigs.json out.jsonl
import sys, os, json, gzip, glob
from multiprocessing import Pool
SIGS = set(json.load(open(sys.argv[1]))); OUT = sys.argv[2]
FILES = sorted(glob.glob("/home/moiz/sniper-data/collect/run_20261021_2207/txs/*.jsonl.gz") + glob.glob("/home/moiz/sniper-data/collect/run_20261022_1543/txs/*.jsonl.gz"))
def work(f):
    out = []
    try:
        for line in gzip.open(f, "rt"):
            a = line.find('"sig":"')
            if a < 0: continue
            sg = line[a + 7:line.find('"', a + 7)]
            if sg in SIGS:
                r = json.loads(line); out.append({k: r.get(k) for k in ("sig", "s", "i", "fee", "cu", "cup", "cul", "tips", "progs", "ixn", "signers", "err")})
    except (EOFError, OSError): pass
    return out
if __name__ == "__main__":
    n = 0
    with Pool(int(os.environ.get("NPROC", "6"))) as p, open(OUT, "w") as fo:
        for rows in p.imap_unordered(work, FILES):
            for r in rows: fo.write(json.dumps(r) + "\n"); n += 1
    print("found", n, "of", len(SIGS))
