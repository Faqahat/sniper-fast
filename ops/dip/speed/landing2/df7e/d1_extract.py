#!/usr/bin/env python3
# DF7eRXHn study, pass 1 (read-only, local files). From the x1 compact files (R3 + R4 = 10-23 19:26 -> 10-25 19:02 PKT):
#   W_df7e.jsonl     every tx signed by the target wallet (failed too)
#   T_mints.jsonl.gz every successful pump trade (all wallets) on any mint the target touched
# usage: python3 -I d1_extract.py OUT_DIR [wallet] [workers]
import sys, os, json, glob, gzip
from multiprocessing import Pool
D = "/home/moiz/sniper-data/landing2"
OUT = sys.argv[1]; W = sys.argv[2] if len(sys.argv) > 2 else "DF7eRXHnvRQ9QeVCrdfS56a7RpBD6se6mgPvzApHPNr9"
P = int(sys.argv[3]) if len(sys.argv) > 3 else 4
def files(kind): return sorted(glob.glob(f"{D}/x_r3/{kind}_*") + glob.glob(f"{D}/x_r4/{kind}_*"))
MS = None
def scan(f):
    out = []
    for l in gzip.open(f, "rt"):
        if any(m in l for m in ()): pass
        r = json.loads(l)
        if r[5] in MS: out.append(l)
    return out
def init(ms):
    global MS; MS = ms
if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for f in files("W"):
        for l in gzip.open(f, "rt"):
            if W in l:
                r = json.loads(l)
                if r[3] and r[3][0] == W: rows.append(r)
    rows.sort()
    with open(f"{OUT}/W_df7e.jsonl", "w") as fo:
        for r in rows: fo.write(json.dumps(r, separators=(",", ":")) + "\n")
    ms = set(m for r in rows for m in r[9][:1])
    print(f"wallet txs {len(rows)}, mints {len(ms)}", flush=True)
    n = 0
    with Pool(P, initializer=init, initargs=(ms,)) as pool, gzip.open(f"{OUT}/T_mints.jsonl.gz", "wt", compresslevel=3) as fo:
        for k, out in enumerate(pool.imap(scan, files("T"), chunksize=8)):
            for l in out: fo.write(l)
            n += len(out)
            if k % 200 == 0: print(k, n, flush=True)
    print("DONE", n, flush=True)
