#!/usr/bin/env python3
# READ-ONLY, offline: every collector row (T = trade event, X = other/failed tx) signed by or for FiFawH on the mints it
# attempted, plus the full trade path of those mints -> fifaw_rows.json {mint: {"me": [rows], "n_rows": k}}
import sys, os, json, gzip, glob, zlib, collections
from multiprocessing import Pool
D = "/home/moiz/sniper-data/collect"; W = "FiFawHqxeTVBhv6YbqbLwDVuvokRpPUM1bNwAyxhGc6W"
A = json.load(open("/home/moiz/sniper/ops/overnight/core/attempts_fifaw.json"))
M = set(A)
def bucket(m): return zlib.crc32(m.encode()) % 256
byb = collections.defaultdict(set)
for m in M: byb[bucket(m)].add(m)
def work(b):
    out = collections.defaultdict(list)
    for pa in ("phaseA", "phaseA_fwd"):
        for f in glob.glob(os.path.join(D, pa, f"b{b:03d}", "*.jsonl.gz")):
            try:
                for line in gzip.open(f, "rt"):
                    if W[:12] not in line: continue
                    r = json.loads(line)
                    if r[1] not in byb[b]: continue
                    if (r[0] == "T" and (r[14] == W or r[6] == W)) or (r[0] == "X" and r[6] == W): out[r[1]].append([pa] + r)
            except (EOFError, OSError, zlib.error): pass
    return dict(out)
if __name__ == "__main__":
    res = {}
    with Pool(12) as p:
        for o in p.imap_unordered(work, sorted(byb)):
            for m, v in o.items(): res.setdefault(m, []).extend(v)
    json.dump(res, open("fifaw_rows.json", "w"))
    print("mints with rows:", len(res), "rows:", sum(len(v) for v in res.values()))
