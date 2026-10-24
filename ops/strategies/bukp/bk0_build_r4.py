#!/usr/bin/env python3
# Day arrays for the NEW partial day R4 (run_20261024_1425, 10-24 19:25 PKT ->; extracted to bukp/phaseA_r4) with the same
# builder, features and R2-only wallet lists as R1-R3 (patterns/p1_build.py). -> patterns/day_R4.npz
import sys, pickle
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns")
import p1_build as B
from multiprocessing import Pool
B.RUNS["R4"] = ("run_20261024_1425", ["/home/moiz/sniper-data/strategies/bukp/phaseA_r4"])
if __name__ == "__main__":
    run = "R4"; first = {}
    with Pool(8) as p:
        for _, fs in p.imap_unordered(B.stage_a, [(run, b) for b in range(256)]):
            for u, k in fs.items():
                if u not in first or k < first[u]: first[u] = k
    pickle.dump(first, open(f"{B.TMP}/{run}_first.pkl", "wb"), protocol=4)
    tot = 0
    with Pool(8, initializer=B.init_b, initargs=(run,)) as p:
        for _, b, n in p.imap_unordered(B.stage_b, [(run, b) for b in range(256)]): tot += n
    print(f"R4: {tot} trades, {B.concat(run)} tokens")
