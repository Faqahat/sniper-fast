#!/usr/bin/env python3
"""QUIET3 step 4: every recorded trade (botpnl p2 rows: s, i, bt, err, u, mint, tok, sol, cpre, cpost) on the mints of our live
positions and shadow triggers, from the DEV/VAL recordings ONLY (run_20261028_1405, run_20261030_1355, run_20261031_1350; the
11-02 recording is the sealed holdout and is not read). Failed txs dropped. Output: one file per recording, rows + run tag.
usage: s4_p2.py OUTDIR MINTSFILE  (4 workers)"""
import sys, os, json, glob
from multiprocessing import Pool
OUT, MF = sys.argv[1], sys.argv[2]
RECS = ['run_20261028_1405', 'run_20261030_1355', 'run_20261031_1350']
MINTS = set(l.strip() for l in open(MF) if l.strip())

def job(fn):
    out = []
    for l in open(fn, errors='replace'):
        i = l.find('"mint":"')
        if i < 0: continue
        m = l[i + 8:l.find('"', i + 8)]
        if m not in MINTS or '"err":true' in l: continue
        out.append(l)
    return out

if __name__ == '__main__':
    for rec in RECS:
        fs = sorted(glob.glob(f'/home/it/sniper-data/botpnl/{rec}/p2_*.jsonl'))
        n = 0
        with Pool(4) as p, open(f'{OUT}/p2m_{rec}.jsonl', 'w') as o:
            for rows in p.imap(job, fs, chunksize=8):
                o.writelines(rows); n += len(rows)
        print(rec, len(fs), 'files', n, 'rows', flush=True)
