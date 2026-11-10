#!/usr/bin/env python3
"""REARM-CREATOR step 1: compact per-run extract of the records this study needs (read-only on run logs).
out: /home/it/sniper-data/filters3/rearmcr/ext/rNN.jsonl  (tape / attempts dropped)"""
import sys, os, json
from multiprocessing import Pool
D = "/home/it/sniper-data"
SRC = {**{r: f"{D}/filters3/runs/r{r}.presend.jsonl" for r in range(37, 47)},
       47: f"{D}/runs/ams/runs/dip_ams_r47.jsonl", 48: f"{D}/runs/ams/runs/dip_ams_r48.jsonl",
       49: f"{D}/runs/ams_r49/dip_ams_r49.jsonl", 50: f"{D}/runs/ams_r50/dip_ams_r50.jsonl", 51: f"{D}/runs/ams_r51/dip_ams_r51.jsonl"}
KEEP = ("presend_live_arm", "presend_live_disarm", "presend_live_fill", "presend_live_close", "presend_live_realized",
        "presend_live_skip", "presend_live_rearm_defer", "presend_live_exit", "presend_live_late_fill", "presend_live_orphan",
        "presend_arm", "presend_fill", "presend_exit", "presend_disarm", "run_start", "run_end", "presend_live_stop")
def job(r):
    out = f"{D}/filters3/rearmcr/ext/r{r}.jsonl"
    n = 0
    with open(SRC[r], errors="replace") as f, open(out + ".tmp", "w") as o:
        for l in f:
            i = l.find('"ev":"')
            if i < 0: continue
            ev = l[i + 6:l.find('"', i + 6)]
            if ev not in KEEP: continue
            if ev in ("run_start", "run_end") and len(l) > 2_000_000: l = l[:0]
            if not l: continue
            o.write(l if l.endswith("\n") else l + "\n"); n += 1
    os.rename(out + ".tmp", out)
    return r, n
if __name__ == "__main__":
    rs = [int(x) for x in sys.argv[1:]] or sorted(SRC)
    with Pool(3) as p:
        for r, n in p.imap_unordered(job, rs): print(r, n, flush=True)
