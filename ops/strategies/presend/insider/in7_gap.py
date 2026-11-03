#!/usr/bin/env python3
"""INSIDER step 7: census paper vs replay on the SAME events (fills on the trigger insider's own dump): paper mSOL vs our gross / slip /
costs, and our hold (fill landing -> sell landing). usage: in7_gap.py CTX.pkl RUNDIR CENSUS.pkl VARIANT"""
import sys, pickle, glob, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/multiarm")
import ma_lib as M
ctxp, rundir, cenp, v = sys.argv[1:5]
ctx = pickle.load(open(ctxp, "rb")); tape = M.Tape(ctx["tab"])
cmap = {(r["mint"], r["w"]): r for r in pickle.load(open(cenp, "rb")) if r["class"] == "insider"}
P = collections.defaultdict(list)
for f in sorted(glob.glob(f"{rundir}/{v}__*.pkl")):
    for r in pickle.load(open(f, "rb"))["rows"]:
        if r["kind"] != "ins" or not r["filled"]: continue
        m = r["mint"]; t = tape.trades(m)
        key = t["slot"].astype(np.int64) * 100000 + t["idx"].astype(np.int64)
        kf = int(np.searchsorted(key, r["fs"] * 100000 + r["fi"]))
        lo = int(np.searchsorted(t["slot"], r["fs"] - 1))
        sells = [q for q in range(lo, kf) if not t["buy"][q]]
        if not sells: continue
        q = max(sells, key=lambda q: t["tok"][q])
        if int(t["user"][q]) != r["ins_u"]: continue
        cr = cmap.get((m, tape.ids[r["ins_u"]][:8]))
        if not cr or cr["paper"] is None: continue
        P["paper"].append(cr["paper"]); P["gross"].append(r["gross_naive"] * 1e3); P["slip"].append(r["d_slip"] * 1e3); P["cut"].append(r["d_cut"] * 1e3)
        P["cash"].append(r["cash"] * 1e3); P["fails"].append(r["fails"]); P["hold_ms"].append(r["c_sell"] - tape.cc(r["fs"], r["fi"]))
        P["cen_ms"].append(cr["dms"])
n = len(P["paper"])
print(v, "fills on the trigger insider's own dump with a census paper fill (all reps):", n)
for k in ("paper", "gross", "slip", "cut", "cash", "fails", "hold_ms"):
    a = np.array(P[k]); print(f"  {k:8s} mean {a.mean():+8.1f}  median {np.median(a):+8.1f}")
