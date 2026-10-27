#!/usr/bin/env python3
# haqq SELL study, step 8: per-LOT slot paths. For every clean closed lot: from its reference slot (the trigger slot for dip buys,
# else the slot of the last outside trade before its buy) to its exit + 12 slots (max 420 slots): per slot the lot's value
# (its tokens sold into the curve state at the end of the slot, pump fees) / its cost, min/max within the slot, outside buy /
# sell SOL and counts, biggest trades, haqq's own other trades, and where this lot's sell(s) landed.
# Output: sniper-data/haqq/lotpaths.pkl  (list of dicts with numpy arrays)
import sys, json, pickle, collections, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/haqq"); import h_lib as H, h5_episodes as E5
from multiprocessing import Pool
DMAX = 420
LOTS = None
def work(b):
    tp = pickle.load(open(f"{H.OUT}/tp/b{b:02d}.pkl", "rb"))
    out = []
    for li, l in LOTS.get(b, []):
        d = tp.get(l["m"])
        if d is None: continue
        T = d["T"]; Wl = d["W"]; users = [Wl[x] for x in T[:, 5]]
        s = T[:, 0]; ii = T[:, 1]; buy = T[:, 6].astype(bool); sol = T[:, 7].astype(np.float64); V = T[:, 9].astype(np.float64); Tk = T[:, 10].astype(np.float64)
        fr = (T[:, 13] + T[:, 14]) / 1e4
        k = l["buy"]["k"]
        if k >= len(T) or users[k] != H.W: continue
        q = float(T[k, 8]); cost = l["cost"] * 1e9
        prev = next((j for j in range(k - 1, -1, -1) if users[j] != H.W), None)
        ref = l["buy"]["s"] - l["buy"]["trig_ds"] if l["buy"]["dip"] else (int(s[prev]) if prev is not None else int(s[k]))
        exit_s = l["sells"][-1]["s"]; first_s = l["sells"][0]["s"]
        D = min(exit_s - ref + 12, DMAX)
        if exit_s - ref > DMAX - 12: D = DMAX
        ret_end = np.full(D + 1, np.nan); ret_min = np.full(D + 1, np.nan); ret_max = np.full(D + 1, np.nan)
        ob = np.zeros(D + 1); os_ = np.zeros(D + 1); nb = np.zeros(D + 1, np.int32); ns = np.zeros(D + 1, np.int32); mb = np.zeros(D + 1); ms = np.zeros(D + 1)
        own = np.zeros(D + 1, np.int32); ntr = np.zeros(D + 1, np.int32); cre_s = np.zeros(D + 1); coh_b = np.zeros(D + 1); coh_s = np.zeros(D + 1)
        sold = np.zeros(D + 1)                       # fraction of this lot sold in that slot
        sellpos = {}
        for x in l["sells"]:
            dd = x["s"] - ref
            if 0 <= dd <= D: sold[dd] += x["part"]; sellpos[dd] = x["i"]
        # state before the buy's slot: last trade before ref slot
        j = k
        while j - 1 >= 0 and s[j - 1] >= ref: j -= 1
        cur = None
        creator = None
        for jj in range(j, len(T)):
            dd = int(s[jj] - ref)
            if dd > D: break
            if dd < 0: continue
            u = users[jj]
            if jj > k or jj == k:
                v = V[jj] * q / (Tk[jj] + q) * (1 - fr[jj]) / cost - 1
                ret_min[dd] = v if np.isnan(ret_min[dd]) else min(ret_min[dd], v); ret_max[dd] = v if np.isnan(ret_max[dd]) else max(ret_max[dd], v); ret_end[dd] = v
            ntr[dd] += 1
            if u == H.W:
                if jj != k: own[dd] += 1
                continue
            if buy[jj]:
                ob[dd] += sol[jj]; nb[dd] += 1; mb[dd] = max(mb[dd], sol[jj])
            else:
                os_[dd] += sol[jj]; ns[dd] += 1; ms[dd] = max(ms[dd], sol[jj])
        # forward fill ret_end for empty slots after the buy
        last = np.nan
        bslot = l["buy"]["s"] - ref
        for dd in range(D + 1):
            if dd < bslot: continue
            if np.isnan(ret_end[dd]): ret_end[dd] = last; ret_min[dd] = last; ret_max[dd] = last
            else: last = ret_end[dd]
        out.append(dict(li=li, ref=ref, bslot=bslot, exit=exit_s - ref, first=first_s - ref, D=D, ret_end=ret_end.astype(np.float32), ret_min=ret_min.astype(np.float32), ret_max=ret_max.astype(np.float32),
                        ob=(ob / 1e9).astype(np.float32), os=(os_ / 1e9).astype(np.float32), nb=nb, ns=ns, mb=(mb / 1e9).astype(np.float32), ms=(ms / 1e9).astype(np.float32), own=own, ntr=ntr, sold=sold.astype(np.float32), sellpos=sellpos))
    return out
if __name__ == "__main__":
    lots = json.load(open(f"{H.OUT}/lots.json"))
    import zlib
    by = collections.defaultdict(list)
    for li, l in enumerate(lots):
        if l["closed"] and not l["censored"] and not l["brk"]: by[zlib.crc32(l["m"].encode()) % 64].append((li, l))
    LOTS = by
    R = []
    with Pool(6) as p:
        for o in p.imap_unordered(work, range(64)): R += o
    pickle.dump(R, open(f"{H.OUT}/lotpaths.pkl", "wb"), protocol=4)
    print("lot paths", len(R))
