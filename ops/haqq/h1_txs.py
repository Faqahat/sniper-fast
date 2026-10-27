#!/usr/bin/env python3
# haqq SELL study, pass 1 (read-only, local recording only): every tx signed by haqqiUUX in the 4 collector runs -> one gz
# jsonl per run (raw records, failed txs included) in /home/moiz/sniper-data/haqq/. usage: nice python3 -I h1_txs.py [procs]
import sys, os, json, gzip, glob, zlib
from multiprocessing import Pool
D = "/home/moiz/sniper-data/collect"; OUT = "/home/moiz/sniper-data/haqq"
RUNS = {"R1": "run_20261021_2207", "R2": "run_20261022_1543", "R3": "run_20261023_1426", "R4": "run_20261024_1425"}
W = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
def work(a):
    tag, path = a; out = []; n = 0
    try:
        for line in gzip.open(path, "rt"):
            n += 1
            if "haqqiUUX" not in line: continue
            try: r = json.loads(line)
            except Exception: continue
            if W in (r.get("signers") or []): r["_run"] = tag; out.append(r)
    except (EOFError, OSError, zlib.error): pass
    return tag, path, n, out
if __name__ == "__main__":
    P = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    jobs = [(t, f) for t, r in RUNS.items() for f in sorted(glob.glob(f"{D}/{r}/txs/*.jsonl.gz"))]
    fh = {t: gzip.open(f"{OUT}/htx_{t}.jsonl.gz", "wt") for t in RUNS}
    tot = 0; k = 0
    with Pool(P) as p:
        for tag, path, n, out in p.imap_unordered(work, jobs, chunksize=2):
            k += 1; tot += n
            for r in out: fh[tag].write(json.dumps(r, separators=(",", ":")) + "\n")
            if k % 50 == 0: print(f"{k}/{len(jobs)} chunks, {tot} txs", flush=True)
    for f in fh.values(): f.close()
    print("DONE", tot, flush=True)
