#!/usr/bin/env python3
# DF7e replay, step 0 (read-only on raw data): decode the raw files of run_20261023_1426 + run_20261024_1425 that the VM1 decode
# did not cover (or saw truncated), with the VM1 decoder (ops/dip/vm1/decode.py), 6 workers. Existing npz are symlinked.
import sys, os, glob
sys.path.insert(0, "/home/moiz/sniper/ops/dip/vm1")
import decode
from multiprocessing import Pool
OUT = "/home/moiz/sniper-data/df7e_replay/dec"
if __name__ == "__main__":
    files = []
    for rec in ("run_20261023_1426", "run_20261024_1425"):
        for f in sorted(glob.glob(f"/home/moiz/sniper-data/collect/{rec}/txs/txs_*.jsonl.gz")):
            o = os.path.join(OUT, rec + "__" + os.path.basename(f).replace(".jsonl.gz", ".npz"))
            if not os.path.exists(o): files.append(f)
    print(len(files), "to decode", flush=True)
    with Pool(6) as p:
        for o, msg in p.imap_unordered(decode.one, [(f, OUT) for f in files]):
            print(os.path.basename(o), msg, flush=True)
    print("DONE")
