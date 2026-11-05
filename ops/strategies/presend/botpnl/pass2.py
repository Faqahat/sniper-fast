#!/usr/bin/env python3
"""BOT P&L pass 2: every tx on a mint that a watched wallet (pass 1) traded -> compact trade rows out/<run>/p2_<file>.jsonl.
Row: s, i, bt, err, signer (fee payer), mint, tok (signer's token delta), sol (signer's lamport delta, fees+tips included),
cpre/cpost (the curve = the other owner of this mint with the largest pre balance; price ~ 1/(cbal+73e12)^2 on the curve).
usage: pass2.py OUTDIR RUNDIR [RUNDIR ...]"""
import sys, os, gzip, json, glob
from multiprocessing import Pool
MINTS = None

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

def init(ms):
    global MINTS; MINTS = ms

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
    out = sys.argv[1]
    for rd in sys.argv[2:]:
        r = os.path.basename(rd.rstrip("/")); ms = set()
        for fn in glob.glob(f"{out}/{r}/p1_*.jsonl"):
            for l in open(fn, errors="replace"):
                ms.update(json.loads(l).get("mints") or [])
        jobs = [(f"{rd}/txs/{fn}", f"{out}/{r}/p2_{fn[:-3]}") for fn in sorted(os.listdir(f"{rd}/txs"))]
        with Pool(14, initializer=init, initargs=(ms,)) as p: tot = sum(max(n, 0) for n in p.imap_unordered(job, jobs))
        print(r, "mints", len(ms), "rows", tot, flush=True)
