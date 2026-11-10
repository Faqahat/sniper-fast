#!/usr/bin/env python3
"""BOT P&L pass 1 (owner 11-03: are the dip bots still making money, and where?). Read-only on local raw recordings.
Pass 1: every tx SIGNED by a watched wallet (prefix match on signers) -> out/<run>/p1_<file>.jsonl (full record).
usage: pass1.py OUTDIR RUNDIR [RUNDIR ...]"""
import sys, os, gzip, json
from multiprocessing import Pool
W = {"haqqiUUX": "haqq", "2VggYpPu": "haqq", "haqq6qnV": "haqq", "8yYMhuYo": "8yYMhu", "DF7eRXHn": "DF7eRX",
     "E2x1ewwX": "E2x1", "HkQ7hMjy": "HkQ7", "DYXDDrZC": "DYXDD", "CvHEVC7S": "CvHEVC7S", "HLU8QbLd": "HLU8QbLd",
     "6VzXcLk9": "6VzXcLk9", "4ggJqUDD": "4ggJqUDD", "DSvgfynk": "DSvgfynk",
     "EgxfYgEb": "OURS", "2g7rYv7y": "OURS"}
PFX = ['"' + p for p in W]

def job(a):
    src, dst = a
    if os.path.exists(dst): return dst, -1
    n = 0
    with gzip.open(src, "rt", errors="replace") as f, open(dst + ".tmp", "w") as o:
      try:
        for l in f:
            i = l.find('"signers":[')
            if i < 0: continue
            j = l.find("]", i)
            seg = l[i:j]
            if any(p in seg for p in PFX):
                o.write(l); n += 1
      except EOFError: pass                             # the live file still being written: keep what was read
    os.rename(dst + ".tmp", dst)
    return dst, n

if __name__ == "__main__":
    out = sys.argv[1]; jobs = []
    for rd in sys.argv[2:]:
        r = os.path.basename(rd.rstrip("/")); os.makedirs(f"{out}/{r}", exist_ok=True)
        for fn in sorted(os.listdir(f"{rd}/txs")):
            jobs.append((f"{rd}/txs/{fn}", f"{out}/{r}/p1_{fn[:-3]}"))
    tot = 0
    with Pool(14) as p:
        for k, (d, n) in enumerate(p.imap_unordered(job, jobs)):
            tot += max(n, 0)
            if k % 100 == 0: print(k, len(jobs), tot, flush=True)
    print("done", len(jobs), tot)
