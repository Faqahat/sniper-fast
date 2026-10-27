#!/usr/bin/env python3
"""VM1 independent check, step 3: the dump table. Every envelope sell (>= 1 SOL, normal SOL curve, post-dump vsol
25..200 SOL) with: window label (T1/T2 = VM1 training, U1..U4 = unseen, GB = 10-min guard band), hole flag,
full-history flag, leader + near flags, my features (model semantics and plain reading) and VM1 scores.
Writes /home/moiz/sniper-data/vm1/dumps.npz"""
import json, numpy as np
import core

T1 = (460_476_411, 460_595_437)       # VM1 training block 1 (copy's ex23.log: rows_d23.json)
T2 = (460_883_322, 461_001_668)       # VM1 training block 2 (copy's race_extract.log: race_rows.json); trained_until 461,001,660
GUARD = int(600 / core.SLOT_SEC)      # 10 minutes in slots
REC = {"U1": (459_792_134, 460_061_200), "U2": (460_090_429, 460_460_779)}   # run_20261021_2207 and run_20261022_1543 (holes excluded)

def label(slot):
    s = np.asarray(slot, np.int64); lab = np.full(len(s), "U?", dtype="<U2")
    lab[(s >= REC["U1"][0]) & (s <= REC["U1"][1])] = "U1"
    lab[(s >= REC["U2"][0]) & (s <= REC["U2"][1])] = "U2"
    lab[(s > T1[1]) & (s < T2[0])] = "U3"
    lab[s > T2[1]] = "U4"
    for a, b in (T1, T2):
        lab[(s >= a - GUARD) & (s <= b + GUARD)] = "GB"
        lab[(s >= a) & (s <= b)] = "T1" if a == T1[0] else "T2"
    return lab

def near_set(path, ids):
    want = set(l.strip().split()[0] for l in open(path) if l.strip() and not l.startswith("#"))
    return np.array([x in want for x in ids] + [False])     # index -1 -> False

if __name__ == "__main__":
    D = core.Data(); M = core.Model()
    k = D.dumps(); T = D.T
    slot = T["slot"][k].astype(np.int64)
    lab = label(slot)
    # holes: anything inside [slot - 300, slot + 40] (60 s features + ~8 s trade window)
    hole = np.zeros(len(k), bool)
    for a, b in D.holes:
        hole |= (slot + 40 >= a) & (slot - 300 <= b)
    hole |= (slot - 300 < D.slot_lo) | (slot + 40 > D.slot_hi)
    full = D.full_hist[T["mint"][k]]
    ld = D.leader(slot)
    fra = near_set("/home/moiz/sniper/ops/region/near_leaders_fra.txt", D.leader_ids)
    ams = near_set("/home/moiz/sniper/ops/region/near_leaders_ams_nobam.txt", D.leader_ids)
    Xm = core.features(D, k, "model"); Xp = core.features(D, k, "plain")
    sm = M.score(Xm); sp = M.score(Xp)
    np.savez("/home/moiz/sniper-data/vm1/dumps.npz", k=k, slot=slot, idx=T["idx"][k], mint=T["mint"][k], lab=lab, hole=hole, full=full,
             leader=ld, near_fra=fra[ld], near_ams=ams[ld], Xm=Xm, Xp=Xp, sm=sm, sp=sp, chain_ok=D.chain_ok[k],
             fee=(T["fee_bps"][k].astype(int) + T["cfee_bps"][k].astype(int)))
    import collections
    print("dumps", len(k), collections.Counter(lab.tolist()))
    print("hole", hole.sum(), "no full history", (~full).sum(), "near FRA", fra[ld].mean().round(3), "near AMS", ams[ld].mean().round(3))
    for L in ("U1", "U2", "U3", "U4", "T1", "T2"):
        m = (lab == L) & ~hole & full
        print(L, "dumps", m.sum(), "VM1 picks (model feats)", (sm[m] >= M.cut).sum(), "(plain feats)", (sp[m] >= M.cut).sum())
