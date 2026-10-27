#!/usr/bin/env python3
# Day arrays for R4 (run_20261024_1425) over BOTH extracts: bukp/phaseA_r4 (to ~21:01 PKT) + dipdetect/phaseA_r4b (the newer
# chunks, dd0_extract_r4.py). Same builder / features / R2-only wallet lists as R1-R3 (patterns/p1_build.py; read-only use).
# -> /home/moiz/sniper-data/strategies/dipdetect/day_R4.npz (+ _meta.json); temp files in dipdetect/tmp (never patterns/).
import sys, os, pickle
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns")
import p1_build as B
from multiprocessing import Pool
OUTD = "/home/moiz/sniper-data/strategies/dipdetect"
B.TMP = f"{OUTD}/tmp"
B.RUNS["R4"] = ("run_20261024_1425", ["/home/moiz/sniper-data/strategies/bukp/phaseA_r4", f"{OUTD}/phaseA_r4b"])
if __name__ == "__main__":
    os.makedirs(B.TMP, exist_ok=True)
    P = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    run = "R4"; first = {}
    with Pool(P) as p:
        for _, fs in p.imap_unordered(B.stage_a, [(run, b) for b in range(256)]):
            for u, k in fs.items():
                if u not in first or k < first[u]: first[u] = k
    pickle.dump(first, open(f"{B.TMP}/{run}_first.pkl", "wb"), protocol=4)
    tot = 0
    with Pool(P, initializer=B.init_b, initargs=(run,)) as p:
        for _, b, n in p.imap_unordered(B.stage_b, [(run, b) for b in range(256)]): tot += n
    B.PO = OUTD                     # concat writes day_R4.npz / _meta.json here (lists / labels were read from patterns/ above)
    print(f"R4: {tot} trades, {B.concat(run)} tokens", flush=True)
