#!/usr/bin/env python3
"""exit2 step 1 (read-only input): pull every trade on every mint E2x1 ever traded out of the haqqml fresh tape
(all pump.fun trades 10-22 03:07 -> 10-28 18:41 PKT), sorted by mint/slot/idx/j.
Out: sniper-data/e2x1_dissect/exit2/tape_his.npz (+ ids.json with the user ids of E2x1 / Grozoe)."""
import json, time, numpy as np
TP = "/home/moiz/sniper-data/haqqml/fresh/tape"; OUT = "/home/moiz/sniper-data/e2x1_dissect/exit2"
W = "E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb"; SIB = "Grozoe2Lk9yu7kWPcCMuWEbrnuBYseBExkYAuHPRJUdJ"
t0 = time.time()
users = json.load(open(f"{TP}/users.json")); uid = {u: i for i, u in enumerate(users)}
wid, sid = uid[W], uid[SIB]
T = np.load(f"{TP}/trades.npy", mmap_mode="r")
mint_col = np.asarray(T["mint"]); user_col = np.asarray(T["user"])
his = np.flatnonzero(user_col == wid)
mints = np.unique(mint_col[his])
print("his rows", len(his), "mints", len(mints), time.time() - t0, flush=True)
keep = np.flatnonzero(np.isin(mint_col, mints))
print("rows on his mints", len(keep), time.time() - t0, flush=True)
cols = ("slot", "idx", "j", "mint", "user", "buy", "sol", "tok", "vsol", "vtok", "rsol", "rtok", "fee_bps", "cfee_bps", "sigh", "bt")
c = {k: np.asarray(T[k][keep]) for k in cols}
o = np.lexsort((c["j"], c["idx"], c["slot"], c["mint"]))
c = {k: v[o] for k, v in c.items()}
# per-wallet activity over the whole tape (for "known bot" features): number of distinct mints traded and trades
uu, cnt = np.unique(user_col, return_counts=True)
pair = np.unique(user_col.astype(np.uint64) << 32 | mint_col.astype(np.uint64))
um, mc = np.unique((pair >> 32).astype(np.uint32), return_counts=True)
np.savez(f"{OUT}/tape_his.npz", **c, wid=wid, sid=sid, act_user=uu, act_trades=cnt, act_mint_user=um, act_mints=mc)
json.dump({"wid": int(wid), "sid": int(sid), "n_rows": int(len(keep)), "n_mints": int(len(mints))}, open(f"{OUT}/ids.json", "w"))
print("saved", len(keep), time.time() - t0)
