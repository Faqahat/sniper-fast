#!/usr/bin/env python3
# READ-ONLY, offline: decoded pump.fun trade events of 9qz7cW in the collector's raw txs (quote leg included), so the
# quote-token side of its non-SOL-quoted trades is known without RPC. -> ev_q9z.json {sig: [event, ...]}
import os, sys, json, gzip, glob, zlib
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from v3event import decode
W = "9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw"; D = "/home/moiz/sniper-data/collect"
def work(f):
    out = {}
    try:
        for line in gzip.open(f, "rt"):
            if W not in line: continue
            r = json.loads(line)
            if (r.get("signers") or [None])[0] != W or r.get("err"): continue
            evs = [e for e in (decode(s) for s in r.get("ev") or []) if e and e["user"] == W]
            if evs: out[r["sig"]] = evs
    except (EOFError, OSError, zlib.error): pass
    return out
if __name__ == "__main__":
    files = sorted(glob.glob(os.path.join(D, "run_20261021_2207", "txs", "*.jsonl.gz"))) + sorted(glob.glob(os.path.join(D, "run_20261022_1543", "txs", "*.jsonl.gz")))
    res = {}
    with Pool(8) as p:
        for o in p.imap_unordered(work, files): res.update(o)
    json.dump(res, open(os.path.join(HERE, "ev_q9z.json"), "w"))
    print("txs with its events", len(res), "non-SOL quote events", sum(1 for v in res.values() for e in v if e["quote"]))
