#!/usr/bin/env python3
"""SELECT s1 (read-only): sort the haqqml fresh tape (all pump.fun trades 10-22 03:07 -> 10-28 18:41 PKT, built from the
recorder by the haqqml agent) by mint/slot/idx; attach create info (dv8 creates.json + s0 creates_new.json).
Out: sniper-data/e2x1_dissect/select/tape.npz, names.json"""
import json, time, numpy as np
TP = "/home/moiz/sniper-data/haqqml/fresh/tape"; OUT = "/home/moiz/sniper-data/e2x1_dissect/select"
W = "E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb"
t0 = time.time()
mints = json.load(open(f"{TP}/mints.json")); users = json.load(open(f"{TP}/users.json"))
uid = {u: i for i, u in enumerate(users)}; wid = uid[W]
T = np.load(f"{TP}/trades.npy", mmap_mode="r")
c = {k: np.asarray(T[k]) for k in ("slot", "idx", "j", "mint", "user", "buy", "sol", "tok", "vsol", "vtok", "bt", "fee_bps", "cfee_bps")}
o = np.lexsort((c["j"], c["idx"], c["slot"], c["mint"]))
c = {k: v[o] for k, v in c.items()}
print("sorted", time.time() - t0, flush=True)
CR = json.load(open("/home/moiz/sniper-data/dv8/tab/creates.json"))
CR.update(json.load(open(f"{OUT}/creates_new.json")))
n = len(mints)
cr_slot = np.full(n, -1, np.int64); cr_user = np.full(n, -1, np.int64); may = np.zeros(n, bool); cr_bt = np.zeros(n, np.int64); solq = np.ones(n, bool)
names = {}
for i, k in enumerate(mints):
    v = CR.get(k)
    if not v or v.get("slot") is None: continue
    cr_slot[i] = int(v["slot"]); cr_user[i] = uid.get(v.get("creator"), -1); may[i] = bool(v.get("mayhem")); cr_bt[i] = int(v.get("bt") or 0)
    q = v.get("quote"); solq[i] = q != "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"   # USDC-quoted curves excluded
    if v.get("name"): names[k] = [v["name"], v.get("symbol", "")]
np.savez(f"{OUT}/tape.npz", **c, wid=wid, cr_slot=cr_slot, cr_user=cr_user, may=may, cr_bt=cr_bt, solq=solq)
json.dump(names, open(f"{OUT}/names.json", "w"))
print("saved", len(c["slot"]), "create-known mints", int((cr_slot >= 0).sum()), "of", n, time.time() - t0)
