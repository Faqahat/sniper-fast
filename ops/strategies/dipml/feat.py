#!/usr/bin/env python3
"""DIPML step 1: dump table + features (decision-time only) + split labels.
Dump = sell >= 1 SOL on a normal (non-Mayhem) pump.fun curve, post-dump vsol 25..200 SOL, full token history recorded,
no recording hole in [slot-300, slot+40].
Split by recording run (fixed before any result): TRAIN = runs 10-21..10-24 (slot <= 461,295,954), VAL = run 10-25
(<= 461,701,096), TEST = runs 10-26 + closed chunks of 10-27. Dumps within 60 slots before a boundary are dropped.
Features: the 16 VM1 'plain' features (core.features) + extras below, all from trades strictly before the dump
(the dump row itself included: its own size/price are known when we see it). Follower-bot list is learned on TRAIN only.
Writes /home/moiz/sniper-data/dipml/dumps.npz"""
import json, numpy as np, collections
import core

B_TRAIN, B_VAL = 461_295_954, 461_701_096
EXTRA = ["idx", "same_slot_before", "trades_2s", "seller_bought", "seller_frac", "seller_is_first", "fb_ever", "fb_15s",
         "uniq_buyers_all", "sol_in_all", "last_buy_sol", "sell_rank60"]

def main():
    D = core.Data(); T = D.T
    k = D.dumps(); slot = T["slot"][k].astype(np.int64)
    hole = np.zeros(len(k), bool)
    for a, b in D.holes: hole |= (slot + 40 >= a) & (slot - 300 <= b)
    hole |= (slot - 300 < D.slot_lo) | (slot + 40 > D.slot_hi)
    full = D.full_hist[T["mint"][k]]
    split = np.where(slot <= B_TRAIN, 0, np.where(slot <= B_VAL, 1, 2))
    edge = ((slot > B_TRAIN - 60) & (slot <= B_TRAIN)) | ((slot > B_VAL - 60) & (slot <= B_VAL))
    keep = ~hole & full & ~edge & D.chain_ok[k]
    k = k[keep]; slot = slot[keep]; split = split[keep]
    print("dumps", len(k), collections.Counter(split.tolist()), flush=True)
    # follower bots from TRAIN only: wallets with most buys within 3 slots after a TRAIN dump (same token)
    cnt = collections.Counter()
    for kk in k[split == 0]:
        m = T["mint"][kk]; e = D.mend[m]; s = T["slot"][kk]
        j = kk + 1
        while j < e and T["slot"][j] <= s + 3:
            if T["buy"][j] == 1: cnt[int(T["user"][j])] += 1
            j += 1
    fb = np.zeros(len(D.users), bool)
    for u, c in cnt.most_common(500): fb[u] = True
    print("follower bots (TRAIN top 500): min count", cnt.most_common(500)[-1][1], flush=True)
    X0 = core.features(D, k, "plain")
    X1 = np.full((len(k), len(EXTRA)), np.nan)
    for r, kk in enumerate(k):
        m = T["mint"][kk]; a = D.mstart[m]; s = int(T["slot"][kk]); u = T["user"][kk]
        sl = T["slot"][a:kk]; us = T["user"][a:kk]; by = T["buy"][a:kk] == 1; so = T["sol"][a:kk]
        f = X1[r]
        f[0] = T["idx"][kk]
        f[1] = (sl == s).sum()
        f[2] = (sl >= s - 9).sum()
        mine = us == u
        bsol = int(so[mine & by].sum()); ssol = int(so[mine & ~by].sum())
        f[3] = bsol / 1e9
        f[4] = T["sol"][kk] / max(bsol - ssol, 1) if bsol > 0 else 9.0
        f[5] = float(len(us) > 0 and us[0] == u)
        f[6] = len(np.unique(us[fb[us]])) if len(us) else 0
        w = sl >= s - 70
        f[7] = len(np.unique(us[w][fb[us[w]]])) if w.any() else 0
        f[8] = len(np.unique(us[by])) if by.any() else 0
        f[9] = so[by].sum() / 1e9
        f[10] = so[by][-1] / 1e9 if by.any() else 0
        w60 = (sl >= s - 282) & ~by
        f[11] = (so[w60] > T["sol"][kk]).sum()
    X = np.hstack([X0, X1])
    np.savez("/home/moiz/sniper-data/dipml/dumps.npz", k=k, slot=slot, split=split, X=X, names=np.array(core.FEATS + EXTRA),
             mint=T["mint"][k], fb=np.where(fb)[0])
    print("saved", X.shape)

if __name__ == "__main__":
    main()
