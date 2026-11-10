#!/usr/bin/env python3
"""Per-tx metadata of every landed pump.fun tx (to describe the TRIGGER tx shape: programs used = router/terminal/bot program,
tips, CU price, ixn).  Read-only, streams each gz.  -> exact/txmeta/<run>/<file>.npz: a int64 [n,8] = s, i, pset id, ixset id, ntips,
tipsum, cup, nsig ; psets / ixsets string tables (per file).  4 workers.  usage: p1_txmeta.py RUNDIR ..."""
import sys, os, gzip, json
from multiprocessing import Pool
import numpy as np
OUT = "/home/it/sniper-data/rivals/9pQQ/exact/txmeta"
def job(a):
    src, dst = a
    if os.path.exists(dst): return -1
    P, Q, rows = {}, {}, []
    with gzip.open(src, "rt", errors="replace") as f:
        try:
            for l in f:
                if '"err":null' not in l: continue
                d = json.loads(l)
                ps = ",".join(sorted(set(p[:8] for p in d.get("progs") or [])))
                ix = ",".join(sorted(set(d.get("ixn") or [])))
                tp = d.get("tips") or []
                rows.append((d["s"], d.get("i") or 0, P.setdefault(ps, len(P)), Q.setdefault(ix, len(Q)), len(tp), sum(v for _, v in tp),
                             d.get("cup") or 0, len(d.get("signers") or [])))
        except (EOFError, OSError): pass
    np.savez(dst + ".tmp.npz", a=np.array(rows, np.int64).reshape(-1, 8), psets=np.array(list(P), dtype="U400"), ixsets=np.array(list(Q), dtype="U600"))
    os.rename(dst + ".tmp.npz", dst); return len(rows)
if __name__ == "__main__":
    jobs = []
    for rd in sys.argv[1:]:
        r = os.path.basename(rd.rstrip("/")); os.makedirs(f"{OUT}/{r}", exist_ok=True)
        for fn in sorted(os.listdir(f"{rd}/txs")): jobs.append((f"{rd}/txs/{fn}", f"{OUT}/{r}/{fn[:-9]}.npz"))
    tot = 0
    with Pool(3) as p:
        for k, n in enumerate(p.imap_unordered(job, jobs)):
            tot += max(n, 0)
            if k % 100 == 0: print(k, len(jobs), tot, flush=True)
    print("done", tot, flush=True)
