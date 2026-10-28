#!/usr/bin/env python3
"""per-slot block size estimate (max tx index of any recorded pump tx + 1) and block time, from recordings.
usage: o1_blocks.py out.npy files...   (reads gz via zcat; only the leading "s","i","bt" fields)"""
import sys, re, subprocess, numpy as np
from multiprocessing import Pool
R = re.compile(rb'^\{"s":(\d+),"i":(\d+),"bt":(\d+)')
def one(f):
    p = subprocess.Popen(["zcat", f], stdout=subprocess.PIPE, bufsize=1 << 20)
    d = {}
    for ln in p.stdout:
        m = R.match(ln)
        if not m: continue
        s = int(m.group(1)); i = int(m.group(2))
        v = d.get(s)
        if v is None: d[s] = [i, int(m.group(3))]
        elif i > v[0]: v[0] = i
    p.wait(); return d
if __name__ == "__main__":
    out = sys.argv[1]; files = sys.argv[2:]
    acc = {}
    with Pool(6) as P:
        for d in P.imap_unordered(one, files, chunksize=1):
            for s, (i, bt) in d.items():
                v = acc.get(s)
                if v is None or i > v[0]: acc[s] = (i, bt)
    a = np.array([(s, i, bt) for s, (i, bt) in acc.items()], dtype=[("slot", "<u8"), ("maxi", "<u4"), ("bt", "<u4")])
    a.sort(order="slot"); np.save(out, a); print(len(a), a["slot"].min(), a["slot"].max())
