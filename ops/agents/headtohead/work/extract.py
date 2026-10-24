#!/usr/bin/env python3
# read-only: raw chunks -> every tx touching a dump mint within [S-2, S+8] of one of its dumps (full raw record kept).
# out: work/ext/<chunk>.jsonl.gz
import sys, os, gzip, glob, json, zlib, bisect
from multiprocessing import Pool
W = "/home/moiz/sniper/ops/agents/headtohead/work"
RUN = "/home/moiz/sniper-data/collect/run_20261023_1426/txs"
R = json.load(open(W + "/runs.json"))
WIN = {}
for d in R["dumps"]:
    WIN.setdefault(d["mint"], []).append(d["slot"])
for m in WIN: WIN[m].sort()
LO, HI = -2, 8
def hit(m, s):
    v = WIN.get(m)
    if not v: return False
    k = bisect.bisect_left(v, s - HI)
    return k < len(v) and v[k] <= s - LO
def work(p):
    name = os.path.basename(p)
    outp = os.path.join(W, "ext", name)
    n = k = 0
    with gzip.open(outp + ".tmp", "wt", compresslevel=3) as fo:
        try:
            for line in gzip.open(p, "rt"):
                n += 1
                a = line.find('"mints":[')
                if a < 0: continue
                b = line.find("]", a)
                ms = [x.strip('"') for x in line[a + 9:b].split(",") if x]
                c = line.find(",", 5)
                try: s = int(line[5:c])
                except ValueError: continue
                if any(hit(m, s) for m in ms):
                    fo.write(line); k += 1
        except (EOFError, OSError, zlib.error): pass
    os.replace(outp + ".tmp", outp)
    return name, n, k
if __name__ == "__main__":
    os.makedirs(W + "/ext", exist_ok=True)
    idx = json.load(open(W + "/chunk_index.json"))
    smin = min(d["slot"] for d in R["dumps"]) + LO; smax = max(d["slot"] for d in R["dumps"]) + HI
    files = [os.path.join(RUN, f) for f, (lo, hi, n) in sorted(idx.items()) if lo is not None and hi >= smin and lo <= smax]
    print(len(files), "chunks", smin, smax, flush=True)
    tot = kept = 0
    with Pool(4) as pool:
        for name, n, k in pool.imap_unordered(work, files):
            tot += n; kept += k
    print("lines", tot, "kept", kept)
