#!/usr/bin/env python3
# READ-ONLY, offline: every raw collector tx (run_*/txs) signed by 9qz7cW -> raw_q9z.jsonl.gz, compact:
# [run, s, i, bt, sig, err, fee, cu, cul, mints, progs, ixn, tips, sd_w, tb_w, n_signers, sd_all (successful buy-like txs only)]
import sys, os, json, gzip, glob, zlib
from multiprocessing import Pool
W = "9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw"; HERE = os.path.dirname(os.path.abspath(__file__))
D = "/home/moiz/sniper-data/collect"
def work(a):
    run, f = a; out = []
    try:
        for line in gzip.open(f, "rt"):
            if W not in line: continue
            r = json.loads(line)
            if (r.get("signers") or [None])[0] != W: continue
            sd = {x[0]: x[1] for x in r.get("sd") or []}
            out.append([run, r["s"], r["i"], r.get("bt"), r["sig"], 1 if r.get("err") else 0, r.get("fee"), r.get("cu"), r.get("cul"), r.get("mints") or [],
                        r.get("progs") or [], r.get("ixn") or [], r.get("tips") or [], sd.get(W, 0), [x for x in (r.get("tb") or []) if len(x) > 1 and x[1] == W],
                        len(r.get("signers") or []), (r.get("sd") or []) if (not r.get("err") and any("Buy" in x for x in (r.get("ixn") or []))) else []])
    except (EOFError, OSError, zlib.error): pass
    return out
if __name__ == "__main__":
    files = [("R1", f) for f in sorted(glob.glob(os.path.join(D, "run_20261021_2207", "txs", "*.jsonl.gz")))] + [("R2", f) for f in sorted(glob.glob(os.path.join(D, "run_20261022_1543", "txs", "*.jsonl.gz")))]
    n = 0
    with Pool(8) as p, gzip.open(os.path.join(HERE, "raw_q9z.jsonl.gz"), "wt") as fo:
        for out in p.imap_unordered(work, files):
            for r in out: fo.write(json.dumps(r, separators=(",", ":")) + "\n"); n += 1
    print("files", len(files), "rows", n)
