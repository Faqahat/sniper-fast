#!/usr/bin/env python3
# Claim 3b: build the HLAG event file twice from the same data in the same run: (1) the claim's dipbuy5 (events selected on the TRUE
# sell size / vsol), (2) dipbuy5_stalesel (events selected on the stale-curve sell size / vsol the lagged engine would compute).
# Same env as the claim's builds plus DIP_HLAG and V2_SLIP. -> V2_OUT_BASE, V2_OUT_STALE (jsonl.gz)
import sys, os, json, gzip
from multiprocessing import Pool
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "v2_mods"))
import dipbuy5_s as A
import dipbuy5_stalesel as S
S.L = A.L; S.byb = A.byb
def one(key):
    ra, _ = A.work(key); rs, _ = S.work(key); return ra, rs
if __name__ == "__main__":
    RA, RS = [], []
    with Pool(int(os.environ.get("NPROC", "6"))) as p:
        for ra, rs in p.imap_unordered(one, sorted(A.byb), chunksize=2): RA += ra; RS += rs
    for path, R in ((os.environ["V2_OUT_BASE"], RA), (os.environ["V2_OUT_STALE"], RS)):
        with gzip.open(path, "wt") as f:
            for r in R: f.write(json.dumps(r) + "\n")
    ka = {(r["m"], r["age"]) for r in RA}; ks = {(r["m"], r["age"]) for r in RS}
    print("HLAG", A.HLAG, "events: true-value selection", len(RA), "| stale selection", len(RS), "| only in true", len(ka - ks), "| only in stale", len(ks - ka))
