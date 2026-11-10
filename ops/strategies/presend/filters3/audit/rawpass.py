#!/usr/bin/env python3
"""FILTERS-3 AUDIT: every trade on the audit's mints (our live fills, every live T2 skip, every shadow fill) from the raw 24/7
recordings (read-only), as pass2.py rows: s, i, bt, err, u (fee payer), mint, tok (payer's token delta), sol (payer's lamport delta),
cpre/cpost (curve balance). 4 worker processes.
usage: rawpass.py MINTS.json OUTDIR RUNDIR [RUNDIR ...]"""
import sys, os, gzip, json
from multiprocessing import Pool
MINTS = None
def init(p):
    global MINTS; MINTS = set(json.load(open(p)))
def rows(d):
    sg = (d.get("signers") or [None])[0]
    sd = dict((a, v) for a, v in (d.get("sd") or []))
    out = []
    for m in d.get("mints") or []:
        if m not in MINTS: continue
        tok, cur = 0, None
        for mm, own, pre, post in d.get("tb") or []:
            if mm != m: continue
            if own == sg: tok += (post or 0) - (pre or 0)
            elif cur is None or (pre or 0) > cur[0]: cur = (pre or 0, post or 0)
        out.append({"s": d["s"], "i": d.get("i"), "bt": d.get("bt"), "err": d.get("err") is not None, "u": sg, "mint": m,
                    "tok": tok, "sol": sd.get(sg, 0), "cpre": cur[0] if cur else None, "cpost": cur[1] if cur else None})
    return out
def job(a):
    src, dst = a
    if os.path.exists(dst): return -1
    n = 0
    with gzip.open(src, "rt", errors="replace") as f, open(dst + ".tmp", "w") as o:
        try:
            for l in f:
                i = l.find('"mints":[')
                if i < 0: continue
                seg = l[i + 9:l.find("]", i)]
                if not any(x.strip('"') in MINTS for x in seg.split(",") if x): continue
                for r in rows(json.loads(l)): o.write(json.dumps(r, separators=(",", ":")) + "\n"); n += 1
        except EOFError: pass
    os.rename(dst + ".tmp", dst)
    return n
if __name__ == "__main__":
    mp, out = sys.argv[1], sys.argv[2]; jobs = []
    for rd in sys.argv[3:]:
        r = os.path.basename(rd.rstrip("/")); os.makedirs(f"{out}/{r}", exist_ok=True)
        jobs += [(f"{rd}/txs/{fn}", f"{out}/{r}/{fn[:-3]}") for fn in sorted(os.listdir(f"{rd}/txs"))]
    with Pool(4, initializer=init, initargs=(mp,)) as p:
        tot = 0
        for k, n in enumerate(p.imap_unordered(job, jobs)):
            tot += max(n, 0)
            if k % 50 == 0: print(k, len(jobs), tot, flush=True)
    print("done", tot, flush=True)
