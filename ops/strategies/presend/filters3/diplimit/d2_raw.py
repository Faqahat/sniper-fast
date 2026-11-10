#!/usr/bin/env python3
"""DIPLIMIT step 2 [MEASURED, read-only]: from a raw 24/7 recording, every successful pump.fun tx on the mints of our ARMED windows
(d1 win_<tag>.pkl), in recording files that overlap [first arm - 300 s, last arm + 120 s]. Same row format as whaleflip/w2_raw.py
(s, i, sig, sg, cl, tb, sd) + per file the max block index per slot (block-position clock).
Out: /home/it/sniper-data/filters3/diplimit/raw/<recording>/<file>.jsonl + .maxi.json
usage: d2_raw.py WORKERS RECORDING TAG [TAG ...]"""
import sys, os, json, pickle, bisect
from multiprocessing import Pool
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/filters3/whaleflip")
import w2_raw as W2
D = "/home/it/sniper-data"
OUT = f"{D}/filters3/diplimit/raw"

if __name__ == "__main__":
    nw, rec, tags = int(sys.argv[1]), sys.argv[2], sys.argv[3:]
    ms = set(); times = []
    for tag in tags:
        for x in pickle.load(open(f"{D}/filters3/diplimit/win_{tag}.pkl", "rb"))["wins"]:
            ms.add(x["mint"].encode()); times.append((x["t_arm"] or 0) / 1e9)
    times.sort()
    W2.OUT = OUT
    os.makedirs(f"{OUT}/{rec}", exist_ok=True)
    jobs = []
    for fn in sorted(os.listdir(f"{D}/collect/{rec}/txs")):
        t0 = int(fn.split("_")[1].split(".")[0])
        k = bisect.bisect_left(times, t0 - 120)
        if k < len(times) and times[k] <= t0 + 300 + 300:
            jobs.append((f"{D}/collect/{rec}/txs/{fn}", f"{OUT}/{rec}/{fn[:-3]}"))
    print("mints", len(ms), "windows", len(times), "files", len(jobs), flush=True)
    tot = 0
    with Pool(nw, initializer=W2.init, initargs=(ms,)) as p:
        for k, (d, n) in enumerate(p.imap_unordered(W2.job, jobs)):
            tot += max(n, 0)
            if k % 20 == 0: print(k, len(jobs), tot, flush=True)
    print("done", len(jobs), tot, flush=True)
