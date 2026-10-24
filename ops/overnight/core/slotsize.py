#!/usr/bin/env python3
# per-slot block-size estimate (max tx index seen by the collector in that slot + 1), both runs -> slotsize.json
import os, json, gzip, glob, collections
from multiprocessing import Pool
D = "/home/moiz/sniper-data/collect"
def work(bdir):
    mx = {}
    for f in glob.glob(os.path.join(bdir, "*.jsonl.gz")):
        try:
            for line in gzip.open(f, "rt"):
                r = json.loads(line); s, i = r[2], r[3]
                if i is not None and i > mx.get(s, -1): mx[s] = i
        except (EOFError, OSError): pass
    return mx
if __name__ == "__main__":
    dirs = sorted(glob.glob(os.path.join(D, "phaseA", "b*"))) + sorted(glob.glob(os.path.join(D, "phaseA_fwd", "b*")))
    M = {}
    with Pool(14) as p:
        for mx in p.imap_unordered(work, dirs):
            for s, i in mx.items():
                if i > M.get(s, -1): M[s] = i
    json.dump({str(s): i + 1 for s, i in M.items()}, open("slotsize.json", "w"))
    import statistics
    print("slots", len(M), "median block-size estimate", statistics.median(i + 1 for i in M.values()))
