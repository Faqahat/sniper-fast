#!/usr/bin/env python3
"""Tape timing (MEASURED, chain clock = slot*212 + idx/blocksize*212 ms, dv8lib.cc):
 (a) haqq sells that follow a >=1 SOL outside buy within 3 slots: delay buy -> his sell (his reactive sell latency);
 (b) haqq buys: what came right before (outside sell >=0.5 SOL = reactive dip buy) and right after (outside sell >=0.5 SOL in the SAME slot
     after his buy = he was in before the dump: pre-send-like); same for our fills.
Out: sniper-data/haqq_dissect/exec/t5_tape.txt"""
import sys, collections, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
D = "/home/moiz/sniper-data/haqq_dissect/exec"
T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
sl = np.asarray(T["slot"], np.int64); ix = np.asarray(T["idx"], np.int64); mint = np.asarray(T["mint"]); sg = np.asarray(T["signer"]); us = np.asarray(T["user"])
buy = np.asarray(T["buy"]); sol = np.asarray(T["sol"], np.float64) / 1e9; bt = np.asarray(T["bt"], np.int64)
ids, idx = L.ids_map()
W = {"haqq": idx[L.HAQQ], "FRA": idx[L.WAL["FRA"]], "AMS": idx[L.WAL["AMS"]]}
o = np.lexsort((T["j"], ix, sl, mint)); 
ms = L.cc(sl, ix)
out = []
def P(*a): out.append(" ".join(str(x) for x in a))
def pct(x, p): return float(np.percentile(x, p)) if len(x) else float("nan")
day = ((bt + 5 * 3600) // 86400)
mo = mint[o]; so = sl[o]; go = sg[o]; uo = us[o]; bo = buy[o]; volo = sol[o]; mso = ms[o]; dayo = day[o]
same_prev = np.r_[False, mo[1:] == mo[:-1]]; same_next = np.r_[mo[1:] == mo[:-1], False]
for who in ("haqq", "FRA", "AMS"):
    wid = W[who]
    mine = (go == wid) | (uo == wid)
    pos = np.nonzero(mine)[0]
    # previous / next OUTSIDE trade in the same mint (skip own trades)
    prev = np.full(len(pos), -1); nxt = np.full(len(pos), -1)
    for k, p in enumerate(pos):
        q = p - 1
        while q >= 0 and mo[q] == mo[p] and mine[q]: q -= 1
        if q >= 0 and mo[q] == mo[p]: prev[k] = q
        q = p + 1
        while q < len(mo) and mo[q] == mo[p] and mine[q]: q += 1
        if q < len(mo) and mo[q] == mo[p]: nxt[k] = q
    isb = bo[pos] == 1
    P(f"===== {who}: own trades {len(pos)} (buys {isb.sum()}, sells {(~isb).sum()})")
    # (a) sells after a >=1 SOL outside buy within 3 slots
    s_idx = np.nonzero(~isb & (prev >= 0))[0]
    pv = prev[s_idx]
    big = (bo[pv] == 1) & (volo[pv] >= 1.0) & (so[pos[s_idx]] - so[pv] <= 3)
    dl = mso[pos[s_idx][big]] - mso[pv[big]]
    P(f"(a) sells whose previous outside trade is a >=1 SOL buy <=3 slots earlier: {big.sum()} of {len(s_idx)} sells ({100*big.mean():.1f}%)")
    if big.sum():
        P(f"    delay big buy -> sell, ms: p25 {pct(dl,25):.0f} med {pct(dl,50):.0f} p75 {pct(dl,75):.0f}; same slot {100*np.mean(so[pos[s_idx][big]]==so[pv[big]]):.0f}%")
    # (b) buys
    b_idx = np.nonzero(isb)[0]
    pv = prev[b_idx]; nx = nxt[b_idx]
    has_p = pv >= 0; has_n = nx >= 0
    dip = np.zeros(len(b_idx), bool); dip[has_p] = (bo[pv[has_p]] == 0) & (volo[pv[has_p]] >= 0.5) & (so[pos[b_idx][has_p]] - so[pv[has_p]] <= 2)
    pre = np.zeros(len(b_idx), bool); pre[has_n] = (bo[nx[has_n]] == 0) & (volo[nx[has_n]] >= 0.5) & (so[nx[has_n]] == so[pos[b_idx][has_n]])
    P(f"(b) buys {len(b_idx)}: right after an outside sell >=0.5 SOL (<=2 slots) {dip.sum()} ({100*dip.mean():.1f}%); "
      f"right BEFORE an outside sell >=0.5 SOL in the same slot (in before the dump) {pre.sum()} ({100*pre.mean():.1f}%)")
    dd = mso[pos[b_idx][dip]] - mso[pv[dip]]
    P(f"    reactive dip buys: delay dump -> buy ms p25 {pct(dd,25):.0f} med {pct(dd,50):.0f} p75 {pct(dd,75):.0f}; same slot {100*np.mean(so[pos[b_idx][dip]]==so[pv[dip]]):.0f}%")
    # per day
    for dd_ in sorted(set(dayo[pos[b_idx]].tolist())):
        m = dayo[pos[b_idx]] == dd_
        if m.sum() < 20: continue
        P(f"    day {L.pkt(dd_*86400-18000)[:5]} buys {m.sum():5} dip-after {100*dip[m].mean():5.1f}%  in-before-dump {100*pre[m].mean():4.1f}%")
open(f"{D}/t5_tape.txt", "w").write("\n".join(out) + "\n")
print("\n".join(out))
