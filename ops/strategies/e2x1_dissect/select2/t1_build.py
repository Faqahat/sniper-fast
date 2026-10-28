#!/usr/bin/env python3
"""select2 t1: rebuild the sorted tape (same as select/s1_build.py, + sigh) into the scratchpad (regenerable)."""
import json, time, sys, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select2"); from lib import *
t0 = time.time()
import shutil
for f in ("mints.json", "users.json"): shutil.copy(f"{TP}/{f}", f"{SCR}/{f}")
mints = json.load(open(f"{SCR}/mints.json")); users = json.load(open(f"{SCR}/users.json"))
TEND = 1793194904   # 10-28 18:41:44 PKT = end of select's tape; the brief's TEST day ends here
uid = {u: i for i, u in enumerate(users)}; wid = uid[W]
T = np.load(f"{TP}/trades.npy", mmap_mode="r")
keep = np.asarray(T["bt"]) <= TEND
c = {k: np.asarray(T[k])[keep] for k in ("slot", "idx", "j", "mint", "user", "buy", "sol", "tok", "vsol", "vtok", "bt", "fee_bps", "cfee_bps", "sigh")}
assert c["mint"].max() < len(mints) and c["user"].max() < len(users)
o = np.lexsort((c["j"], c["idx"], c["slot"], c["mint"]))
c = {k: v[o] for k, v in c.items()}
print("sorted", time.time() - t0, flush=True)
CR = json.load(open(f"{SEL}/creates_all.json"))
n = len(mints)
cr_slot = np.full(n, -1, np.int64); cr_user = np.full(n, -1, np.int64); may = np.zeros(n, bool); cr_bt = np.zeros(n, np.int64); solq = np.ones(n, bool)
cashback = np.zeros(n, bool); holder = np.zeros(n, bool); cr_idx = np.full(n, -1, np.int64)
for i, k in enumerate(mints):
    v = CR.get(k)
    if not v or v.get("slot") is None: continue
    cr_slot[i] = int(v["slot"]); cr_idx[i] = int(v.get("idx", -1)); cr_user[i] = uid.get(v.get("creator"), -1); may[i] = bool(v.get("mayhem")); cr_bt[i] = int(v.get("bt") or 0)
    q = v.get("quote"); solq[i] = q != "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    cashback[i] = bool(v.get("cashback")); holder[i] = bool(v.get("holder"))
np.savez(f"{SCR}/tape.npz", **c, wid=wid, sibid=uid.get(SIB, -1), cr_slot=cr_slot, cr_idx=cr_idx, cr_user=cr_user, may=may, cr_bt=cr_bt, solq=solq, cashback=cashback, holder=holder)
print("saved", len(c["slot"]), "create-known", int((cr_slot >= 0).sum()), "of", n, time.time() - t0)
