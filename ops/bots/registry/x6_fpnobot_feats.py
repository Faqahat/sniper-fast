#!/usr/bin/env python3
"""BOTREG step 6 [MEASURED, comparison only]: re-compute FP-NOBOT's chain features on the DEV positions (r37-r54; r55 never
loaded) with a different follower-bot list, using flatperfect fp1_chain.py's own feature code unchanged (imported read-only).
  mode fixed : fp1 as-is (cohort.json + NAMED)  -> parity check against dev_chain_full.pkl
  mode dyn   : the bot list is the BOTREG engine view as of the start of each hour (backtest/members.npz), time-varying:
               a chain row / failed buy counts as a bot row if its wallet was listed at that hour; holder-based inputs use
               the list at the trigger hour. Labels (L_*) are re-computed with the same list (both are saved).
  mode dynnamed : dyn + the NAMED seed list (static), to separate discovery from naming
FROZEN_FLAT.json and the flatperfect folder are not touched (bytecode writing disabled).
usage: x6_fpnobot_feats.py MODE OUT.pkl"""
import sys, os, pickle, json, collections
sys.dont_write_bytecode = True
os.environ.setdefault("CHAIN_DIR", "/home/moiz/sniper-data/flatperfect/chain")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/flatperfect")
import numpy as np
mode, out = sys.argv[1], sys.argv[2]
import fp1_chain as F          # loads the chain (module level) with the fixed list
L = F.L

if mode in ("dyn", "dynnamed"):
    Mz = np.load("/home/moiz/sniper-data/botreg/backtest/members.npz")
    mem = collections.defaultdict(list)
    for t, u in zip(Mz["t"], Mz["u"]): mem[int(t)].append(u)
    mem = {h: np.array(sorted(v), dtype=np.uint64) for h, v in mem.items()}
    NAMd = F.NAM if mode == "dynnamed" else np.zeros(0, np.uint64)
    BT = F.z["bt"]
    hr = (BT // 3600) * 3600
    o = np.argsort(hr, kind="stable"); hs = hr[o]
    isF = np.zeros(F.n, bool)
    for h in np.unique(hs):
        a, b = np.searchsorted(hs, h), np.searchsorted(hs, h, side="right")
        rows = o[a:b]
        lst = mem.get(int(h), np.zeros(0, np.uint64))
        isF[rows] = np.isin(F.U[rows], lst) | np.isin(F.U[rows], NAMd)
    isF &= ~F.isO
    # failed buys: slot -> block time from the chain
    so = np.argsort(F.S, kind="stable"); fbt = np.interp(F.FS_, F.S[so], BT[so]).astype(np.int64)
    fh = (fbt // 3600) * 3600
    o2 = np.argsort(fh, kind="stable"); fhs = fh[o2]
    fF = np.zeros(len(F.FS_), bool)
    for h in np.unique(fhs):
        a, b = np.searchsorted(fhs, h), np.searchsorted(fhs, h, side="right")
        rows = o2[a:b]
        lst = mem.get(int(h), np.zeros(0, np.uint64))
        fF[rows] = np.isin(F.FP_[rows], lst) | np.isin(F.FP_[rows], NAMd)
    fF &= (F.FK_ == 1)
    print("dyn bot rows", isF.sum(), "fixed", F.isF.sum(), "| bot fails", fF.sum(), "fixed", F.fF.sum(), flush=True)
    # re-derive every global fp1 builds from isF / fF (same code as fp1)
    F.isF = isF; F.fF = fF
    F.gfail = np.sort(F.FS_[fF])
    _ba_s = np.r_[F.S[isF], F.FS_[fF]]; _ba_u = np.r_[F.U[isF], F.FP_[fF]]
    _o = np.argsort(_ba_s, kind="stable"); F.BA_S, F.BA_U = _ba_s[_o], _ba_u[_o]
    F.cF = np.r_[0, np.cumsum((isF & (F.B == 1)).astype(np.int64))]
    dmp = np.nonzero((F.B == 0) & (F.drop >= 0.10) & (F.SOL >= 0.5e9) & ~F.isO)[0]
    e2 = np.searchsorted(F.gkey, F.gkey[dmp] + 2, side="right")
    d_slot = F.S[dmp]; d_fol = (F.cF[e2] - F.cF[dmp + 1]) > 0
    oo = np.argsort(d_slot, kind="stable"); d_fol = d_fol[oo]
    F.cdf = np.r_[0, np.cumsum(d_fol)]
    d12 = F.drop[dmp][oo] >= 0.12
    F.cd12f = np.r_[0, np.cumsum(d12 & d_fol)]
    F.gF = np.sort(F.S[isF & (F.B == 1)])
    # holder-based inputs use COH/NAM: switch per position to the list at the trigger hour
    so_s = F.S[so]; so_bt = BT[so]
    def slot_hour(s): return int(np.interp(s, so_s, so_bt)) // 3600 * 3600
    COH0 = F.COH
    def one(p):
        F.COH = mem.get(slot_hour(p["trig_slot"]), np.zeros(0, np.uint64)); F.NAM = NAMd
        return F._one(p)
else:
    def one(p): return F._one(p)

P = pickle.load(open("/home/moiz/sniper-data/flatperfect/dev_inputs.pkl", "rb"))
assert not any(p["key"].startswith("r55|") for p in P)
res = {}
for k, p in enumerate(P):
    key, f = one(p); res[key] = f
    if k % 500 == 0: print(k, len(P), flush=True)
pickle.dump(res, open(out, "wb"))
print("done", sum(1 for v in res.values() if v), "of", len(res), flush=True)
