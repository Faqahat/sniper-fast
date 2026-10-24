#!/usr/bin/env python3
# read-only: per raw chunk -> (min slot, max slot, n lines). Output json to work/chunk_index.json
import sys, os, gzip, glob, json, zlib
from multiprocessing import Pool
RUN = "/home/moiz/sniper-data/collect/run_20261023_1426/txs"
T0 = float(sys.argv[1]) if len(sys.argv) > 1 else 0
def work(p):
    lo = hi = None; n = 0
    try:
        for line in gzip.open(p, "rt"):
            k = line.find(",", 5)
            try: s = int(line[5:k])
            except ValueError: continue
            n += 1
            if lo is None or s < lo: lo = s
            if hi is None or s > hi: hi = s
    except (EOFError, OSError, zlib.error): pass
    return os.path.basename(p), lo, hi, n
if __name__ == "__main__":
    files = sorted(f for f in glob.glob(RUN + "/txs_*.jsonl.gz") if int(os.path.basename(f)[4:14]) >= T0)
    out = {}
    with Pool(4) as pool:
        for name, lo, hi, n in pool.imap_unordered(work, files):
            out[name] = [lo, hi, n]
    json.dump(out, open("/home/moiz/sniper/ops/agents/headtohead/work/chunk_index.json", "w"), indent=0, sort_keys=True)
    print(len(out))
