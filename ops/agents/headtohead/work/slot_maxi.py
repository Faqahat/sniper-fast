#!/usr/bin/env python3
# read-only: per slot max tx index seen in raw chunks (lower bound of block size; pump-related txs only)
import os, gzip, glob, json, zlib
from multiprocessing import Pool
W = "/home/moiz/sniper/ops/agents/headtohead/work"
RUN = "/home/moiz/sniper-data/collect/run_20261023_1426/txs"
def work(p):
    mx = {}
    try:
        for line in gzip.open(p, "rt"):
            a = line.find(",", 5); s = int(line[5:a]); b = line.find(",", a + 5); i = int(line[a + 5:b])
            if i > mx.get(s, -1): mx[s] = i
    except (EOFError, OSError, zlib.error, ValueError): pass
    return mx
if __name__ == "__main__":
    idx = json.load(open(W + "/chunk_index.json"))
    files = [os.path.join(RUN, f) for f in sorted(idx)]
    out = {}
    with Pool(4) as pool:
        for mx in pool.imap_unordered(work, files):
            for s, i in mx.items():
                if i > out.get(s, -1): out[s] = i
    json.dump(out, open(W + "/slot_maxi.json", "w"))
    print(len(out))
