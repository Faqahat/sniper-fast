#!/usr/bin/env python3
# READ-ONLY, offline: every collector row (phase-A R1 + R2) of 9qz7cW: trade rows T (user == wallet) and failed / other
# tx rows X (signer == wallet) -> rows_q9z.json {"T": [...], "X": [...]} with the launch slot attached.
import sys, os, json, gzip, glob, zlib
from multiprocessing import Pool
D = "/home/moiz/sniper-data/collect"; W = "9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw"; HERE = os.path.dirname(os.path.abspath(__file__))
def work(bdir):
    T, X = [], []
    for f in glob.glob(os.path.join(bdir, "*.jsonl.gz")):
        try:
            for line in gzip.open(f, "rt"):
                if W not in line: continue
                r = json.loads(line)
                if r[0] == "T" and r[14] == W: T.append(r)
                elif r[0] == "X" and r[6] == W: X.append(r)
        except (EOFError, OSError, zlib.error): pass
    return T, X
if __name__ == "__main__":
    dirs = [("R1", d) for d in sorted(glob.glob(os.path.join(D, "phaseA", "b*")))] + [("R2", d) for d in sorted(glob.glob(os.path.join(D, "phaseA_fwd", "b*")))]
    out = {"T": [], "X": []}
    with Pool(8) as p:
        for (run, _), (T, X) in zip(dirs, p.imap(work, [d for _, d in dirs])):
            out["T"] += [[run] + r for r in T]; out["X"] += [[run] + r for r in X]
    json.dump(out, open(os.path.join(HERE, "rows_q9z.json"), "w"))
    print("T rows", len(out["T"]), "X rows", len(out["X"]))
