#!/usr/bin/env python3
# read-only: raw chunks -> txs touching probe mints within [S-2, S+8] of the probe dump. out: work/extp/<chunk>.jsonl.gz
import sys, os, gzip, glob, json, zlib, bisect
from multiprocessing import Pool
W = "/home/moiz/sniper/ops/agents/headtohead/work"
RUN = "/home/moiz/sniper-data/collect/run_20261023_1426/txs"
SP = "/home/moiz/sniper/ops/dip/speed"
WIN = {}; probes = []
for p in "ABCDE":
    for l in open(f"{SP}/probe{p}.jsonl"):
        d = json.loads(l)
        if d["ev"] == "probe":
            WIN.setdefault(d["mint"], []).append(d["slot"]); probes.append(d["slot"])
for m in WIN: WIN[m].sort()
LO, HI = -2, 8
def hit(m, s):
    v = WIN.get(m)
    if not v: return False
    k = bisect.bisect_left(v, s - HI)
    return k < len(v) and v[k] <= s - LO
def work(p):
    name = os.path.basename(p); outp = os.path.join(W, "extp", name); k = 0
    with gzip.open(outp + ".tmp", "wt", compresslevel=3) as fo:
        try:
            for line in gzip.open(p, "rt"):
                a = line.find('"mints":[')
                if a < 0: continue
                b = line.find("]", a)
                ms = [x.strip('"') for x in line[a + 9:b].split(",") if x]
                c = line.find(",", 5)
                try: s = int(line[5:c])
                except ValueError: continue
                if any(hit(m, s) for m in ms): fo.write(line); k += 1
        except (EOFError, OSError, zlib.error): pass
    os.replace(outp + ".tmp", outp)
    return name, k
if __name__ == "__main__":
    os.makedirs(W + "/extp", exist_ok=True)
    idx = json.load(open(W + "/chunk_index.json"))
    smin = min(probes) + LO; smax = max(probes) + HI
    files = [os.path.join(RUN, f) for f, (lo, hi, n) in sorted(idx.items()) if lo is not None and hi >= smin and lo <= smax]
    files = [f for f in files if any(lo <= s + HI and hi >= s + LO for s in probes for (lo, hi, n) in [idx[os.path.basename(f)]])]
    print(len(files), "chunks", flush=True)
    kept = 0
    with Pool(4) as pool:
        for name, k in pool.imap_unordered(work, files): kept += k
    print("kept", kept)
