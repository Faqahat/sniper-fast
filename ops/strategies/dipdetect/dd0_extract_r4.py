#!/usr/bin/env python3
# Phase-A extract (read-only) of the R4 raw chunks NOT yet in bukp/phaseA_r4 (that copy stops at chunk 1792857624, ~21:01 PKT)
# -> /home/moiz/sniper-data/strategies/dipdetect/phaseA_r4b. Same row format as ops/select/a_extract.py (its work() is reused).
# usage: python3 dd0_extract_r4.py [procs]
import sys, os, glob
sys.argv = [sys.argv[0], "/home/moiz/sniper-data/collect/run_20261024_1425", "/home/moiz/sniper-data/strategies/dipdetect/phaseA_r4b"] + sys.argv[1:2]
sys.path.insert(0, "/home/moiz/sniper/ops/select")
import a_extract as A
from multiprocessing import Pool
if __name__ == "__main__":
    for b in range(A.NB): os.makedirs(os.path.join(A.OUT, f"b{b:03d}"), exist_ok=True)
    done = {os.path.basename(f).split(".")[0] for f in glob.glob("/home/moiz/sniper-data/strategies/bukp/phaseA_r4/b*/*.jsonl.gz")}
    files = [f for f in sorted(glob.glob(os.path.join(A.RUN, "txs", "*.jsonl.gz"))) if os.path.basename(f).split(".")[0] not in done]
    print("chunks to extract:", len(files), files[0] if files else None, files[-1] if files else None, flush=True)
    tot = 0
    with Pool(int(sys.argv[3]) if len(sys.argv) > 3 else 3) as p:
        for k, n in enumerate(p.imap_unordered(A.work, files), 1):
            tot += n; print(f"{k}/{len(files)} chunks, {tot} txs", flush=True)
    print("DONE", tot, flush=True)
