#!/usr/bin/env python3
"""migrate agent, step 0: per-wallet trip history from grad's tape (curve trades of every near-graduation token + all PumpSwap
events), so that buyer-quality features can be looked up CAUSALLY (only trips that ENDED before time t count).
Trip = (user, mint). Output /home/moiz/sniper-data/e2x1_dissect/migrate/wallets.npz sorted by (user, t_end):
  user, t_end (bt of the last trade), t_first, pnl (SOL out - SOL in, curve+pool, open bags = 0), sol_in, grad (token completed),
  neargrad (bought on the curve at vsol>=80), poolopen (bought in the pool at migration slot +0/+1), completer (its buy completed
  the curve), compslot (bought in the completion slot), ntr (trades)."""
import numpy as np, pickle, time
from mlib import Tape, D

t0 = time.time()
T = Tape(); TR = T.T; P = T.P
print("loaded", time.time() - t0, flush=True)
nm = len(T.mints)
cmp_slot = np.full(nm, -1, np.int64)
for m, c in T.cmp.items():
    k = T.mid.get(m)
    if k is not None: cmp_slot[k] = c["slot"]
grad_m = cmp_slot >= 0
pool_mint = np.full(len(T.pools), -1, np.int64); pool_mig_slot = np.full(len(T.pools), -1, np.int64)
for m, mg in T.mig.items():
    pk = T.pid.get(mg["pool"]); mk = T.mid.get(m)
    if pk is not None and mk is not None: pool_mint[pk] = mk; pool_mig_slot[pk] = mg["slot"]

# ---- curve trips
u = TR["user"].astype(np.int64); m = TR["mint"].astype(np.int64); key = u * nm + m
order = np.argsort(key, kind="stable"); key = key[order]; rows = TR[order]
uk, start = np.unique(key, return_index=True)
buy = rows["buy"] == 1; sol = rows["sol"].astype(np.float64) / 1e9
def red(x, f=np.add): return f.reduceat(x, start)
c_in = red(np.where(buy, sol, 0.0)); c_out = red(np.where(buy, 0.0, sol))
c_tf = red(rows["bt"].astype(np.int64), np.minimum); c_tl = red(rows["bt"].astype(np.int64), np.maximum)
c_n = np.diff(np.append(start, len(rows)))
c_ng = red((buy & (rows["vsol"] >= 80_000_000_000)).astype(np.int64)) > 0
c_cmp = red((buy & (rows["rtok"] == 0)).astype(np.int64)) > 0
mslot = cmp_slot[rows["mint"]]
c_cs = red((buy & (rows["slot"].astype(np.int64) == mslot)).astype(np.int64)) > 0
print("curve trips", len(uk), time.time() - t0, flush=True)

# ---- pool trips
pm = pool_mint[P["pool"]]; okp = pm >= 0
Pp = P[okp]; pmk = pm[okp]
u2 = Pp["user"].astype(np.int64); key2 = u2 * nm + pmk
o2 = np.argsort(key2, kind="stable"); key2 = key2[o2]; Pp = Pp[o2]; pmk = pmk[o2]
uk2, st2 = np.unique(key2, return_index=True)
pbuy = Pp["buy"] == 1; uq = Pp["uquote"].astype(np.float64) / 1e9
def red2(x, f=np.add): return f.reduceat(x, st2)
p_in = red2(np.where(pbuy, uq, 0.0)); p_out = red2(np.where(pbuy, 0.0, uq))
p_tf = red2(Pp["bt"].astype(np.int64), np.minimum); p_tl = red2(Pp["bt"].astype(np.int64), np.maximum)
p_n = np.diff(np.append(st2, len(Pp)))
ms2 = pool_mig_slot[Pp["pool"]]
p_po = red2((pbuy & (Pp["slot"].astype(np.int64) <= ms2 + 1)).astype(np.int64)) > 0
print("pool trips", len(uk2), time.time() - t0, flush=True)

# ---- merge on key
allk = np.union1d(uk, uk2)
def place(k, src, dst_default, vals):
    out = np.full(len(allk), dst_default, dtype=vals.dtype); out[np.searchsorted(allk, k)] = vals; return out
sol_in = place(uk, 0, 0.0, c_in) + place(uk2, 0, 0.0, p_in)
sol_out = place(uk, 0, 0.0, c_out) + place(uk2, 0, 0.0, p_out)
t_first = np.minimum(place(uk, 0, np.int64(2**62), c_tf), place(uk2, 0, np.int64(2**62), p_tf))
t_end = np.maximum(place(uk, 0, np.int64(0), c_tl), place(uk2, 0, np.int64(0), p_tl))
ntr = place(uk, 0, np.int64(0), c_n) + place(uk2, 0, np.int64(0), p_n)
neargrad = place(uk, 0, False, c_ng); completer = place(uk, 0, False, c_cmp); compslot = place(uk, 0, False, c_cs)
poolopen = place(uk2, 0, False, p_po)
user = allk // nm; mint = allk % nm; grad = grad_m[mint]
o = np.lexsort((t_end, user))
np.savez(D + "/wallets.npz", user=user[o], mint=mint[o], t_end=t_end[o], t_first=t_first[o], pnl=(sol_out - sol_in)[o], sol_in=sol_in[o],
         grad=grad[o], neargrad=neargrad[o], poolopen=poolopen[o], completer=completer[o], compslot=compslot[o], ntr=ntr[o])
print("trips", len(allk), "users", len(np.unique(user)), "saved", time.time() - t0, flush=True)
