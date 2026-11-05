#!/usr/bin/env python3
"""FILTERS-3 AUDIT step 3: cut the raw-recording trade rows (rawpass.py output) down to the slot windows the audit needs:
our live positions (fill slot - 2 .. sell slot + 25), every main-shadow T2 trigger (trigger slot - 2 .. + 45), every live re-arm
window (dump slot - 2 .. window end + 25). Also each recording's slot span (coverage). 4 worker processes. Read-only on inputs.
usage: windows.py OUT.pkl RAWDIR [RAWDIR ...]"""
import sys, os, json, glob, pickle, collections
from multiprocessing import Pool
EX = "/home/moiz/sniper-data/filters3/audit/ex"
WIN = None
def build():
    w = collections.defaultdict(list)
    for r in range(37, 47):
        S = pickle.load(open(f"{EX}/r{r}.pkl", "rb"))
        for (seg, wid, m, pid), c in S["lclose"].items():
            f = S["lfill"].get((seg, wid, m)) or {}
            sl = [x[0] for x in (c.get("sell_lands") or [])] or [c.get("exit_slot") or f.get("slot") or 0]
            if f.get("slot"): w[m].append((f["slot"] - 2, max(sl) + 25))
        for a in S["sh_arm"].values(): w[a["mint"]].append((a["slot"] - 2, a["slot"] + 45))
        for d in S["skips"]:
            t = d.get("trig") or {}
            if t.get("mint") and t.get("slot"): w[t["mint"]].append((t["slot"] - 2, t["slot"] + 45))
        for a in S["larm"].values():
            if a.get("kind") == "rearm" and a.get("dump"): w[a["mint"]].append((a["dump"]["slot"] - 2, (a.get("en_slot") or a["dump"]["slot"] + 23) + 25))
    # merge overlapping windows per mint
    out = {}
    for m, v in w.items():
        v.sort(); mg = []
        for lo, hi in v:
            if mg and lo <= mg[-1][1] + 1: mg[-1][1] = max(mg[-1][1], hi)
            else: mg.append([lo, hi])
        out[m] = mg
    return out
def init(wp):
    global WIN; WIN = pickle.load(open(wp, "rb"))
def job(fn):
    keep = collections.defaultdict(list); lo, hi = None, None
    for l in open(fn, errors="replace"):
        x = json.loads(l); s = x["s"]
        lo = s if lo is None or s < lo else lo; hi = s if hi is None or s > hi else hi
        ws = WIN.get(x["mint"])
        if not ws: continue
        for a, b in ws:
            if a <= s <= b:
                keep[x["mint"]].append((s, x["i"] or 0, x["u"], x["tok"], x["sol"], x["err"], x["cpre"], x["cpost"])); break
    return fn, dict(keep), lo, hi
if __name__ == "__main__":
    out = sys.argv[1]; wp = out + ".win"
    pickle.dump(build(), open(wp, "wb"))
    files = []
    for rd in sys.argv[2:]: files += sorted(glob.glob(f"{rd}/run_*/txs_*.jsonl"))
    rows = collections.defaultdict(list); cov = collections.defaultdict(lambda: [None, None])
    with Pool(4, initializer=init, initargs=(wp,)) as p:
        for fn, keep, lo, hi in p.imap_unordered(job, files):
            rec = os.path.basename(os.path.dirname(fn))
            for m, v in keep.items(): rows[m].extend(v)
            c = cov[rec]
            if lo is not None:
                c[0] = lo if c[0] is None else min(c[0], lo); c[1] = hi if c[1] is None else max(c[1], hi)
    for m in rows: rows[m] = sorted(set(rows[m]))
    pickle.dump(dict(rows=dict(rows), cov=dict(cov)), open(out, "wb"))
    print("mints", len(rows), "rows", sum(len(v) for v in rows.values()), "coverage", dict(cov))
