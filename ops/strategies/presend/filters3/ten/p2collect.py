#!/usr/bin/env python3
"""TEN: collect raw-recording trade rows (botpnl p2 extracts, DEV recordings only: 10-28, 10-30, 10-31; the 11-02 recording is SEALED
and never read) for the mints / slot ranges the window and exit replays need. 4 worker processes.
usage: p2collect.py   -> /home/moiz/sniper-data/filters3/ten/p2tape.json  {mint: [[s, i, u, tok, sol, cpre, cpost], ...]} (err rows dropped)"""
import json, glob, os, sys
from multiprocessing import Pool
D = "/home/moiz/sniper-data/filters3/ten/"
RECS = ["/home/moiz/sniper-data/botpnl/run_20261028_1405", "/home/moiz/sniper-data/botpnl/run_20261030_1355", "/home/moiz/sniper-data/botpnl/run_20261031_1350"]
NEED = None

def need():
    rng = {}
    def add(m, a, b):
        if not m or a is None: return
        lo, hi = rng.get(m, (a, b)); rng[m] = (min(lo, a), max(hi, b))
    for r in ["r37", "r38", "r39", "r40", "r41", "r42"]:
        X = json.load(open(D + r + ".x.json"))
        for v in X["live"].values():
            arm = v.get("arm") or {}; tr = arm.get("trig") or {}
            s = tr.get("slot")
            if s: add(v.get("mint") or tr.get("mint"), s - 400, (arm.get("en_slot") or s + 30) + 80)
            for f in v.get("fills") or []: add(v.get("mint"), f["slot"] - 400, f["slot"] + 80)
        for x in X["rearm_skip_rows"]:
            if x["why"] in ("rearm_age", "rearm_no_holder") and x.get("slot") and (x.get("age") or 0) <= 400:
                add(x["mint"], x["slot"] - 450, x["slot"] + 80)
    return rng

def init(n):
    global NEED; NEED = n

def job(path):
    out = []
    for l in open(path):
        i = l.find('"mint":"')
        if i < 0: continue
        m = l[i + 8:l.find('"', i + 8)]
        r = NEED.get(m)
        if r is None: continue
        d = json.loads(l)
        if d["err"] or d["cpre"] is None or d["cpost"] is None: continue
        if not (r[0] <= d["s"] <= r[1]): continue
        out.append((m, (d["s"], d["i"], d["u"], d["tok"], d["sol"], d["cpre"], d["cpost"])))
    return out

if __name__ == "__main__":
    n = need(); print("mints needed", len(n), flush=True)
    files = sorted(f for r in RECS for f in glob.glob(r + "/p2_*.jsonl"))
    tape = {}
    with Pool(4, initializer=init, initargs=(n,)) as pool:
        for k, out in enumerate(pool.imap_unordered(job, files, chunksize=4)):
            for m, row in out: tape.setdefault(m, []).append(row)
            if k % 100 == 0: print(k, len(files), len(tape), flush=True)
    for m in tape: tape[m].sort(key=lambda r: (r[0], r[1] or 0))
    json.dump(tape, open(D + "p2tape.json", "w"))
    print("mints with rows", len(tape), "rows", sum(len(v) for v in tape.values()))
