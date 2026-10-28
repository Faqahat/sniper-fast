#!/usr/bin/env python3
"""pos step 5 (read-only): dump 'battlegrounds'. The k-th dump on the same token, for ANY dip buyer:
  ideal = a 0.40 SOL buy right after the dump (the front of the queue; 'the market at its best'),
  ours  = the dv8 contention-aware landing (rank model, 4 draws, +5% guard; expected value per attempt),
  calibrated = 0.61 x ours - 1.17 mSOL per attempt (dv8 c2, live fit),
  haqq  = his real code-matched lots bought within 2 slots after that dump (MEASURED).
Universe = dv8 uni.npz candidates (outside sell, drop >= 5%, >= 0.5 SOL, curve > 30.52, age <= 30 min; our rows removed),
usable hours, mayhem EXCLUDED. Exit = 5-slot timer (our M2), exact follower model. Tx costs: NOW 1.75+1.77 per fill,
0.53 per failed fire; CHEAP 0.33+0.33 / 0.04 (dv8 g1). Causal features per candidate (all known at the dump):
  k        = order of this candidate among the token's candidates;
  prev_ok  = the previous candidate's 5-slot window has closed before this dump (else 'holding' = we'd still be in it);
  prev_pay = ideal P&L of the previous candidate (its price path is public once its window closed);
  gap      = slots since the previous candidate; hq_open = haqq holds the token now (public wallet).
Out: p5.txt, p5.npz (per-candidate arrays reused by p6)"""
import json, sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
from plib import *
import pickle

P = Out(f"{OUT}/p5.txt")
A_CAL, B_CAL = 0.61, -0.00117
NOWF, NOWX = 0.00175 + 0.00177, 0.00053
CHF, CHX = 0.00066, 0.00004


def main():
    Z = np.load(f"{L.D}/uni.npz")
    X = Z["X"]; M = Z["M"]; FILL = Z["FILL"]; PN = Z["PN"]; ES = Z["ES"]; feats = list(Z["feats"])
    hrs = json.load(open(f"{L.D}/hours.json")); good = {r["h"] for r in hrs["rows"] if r["usable"]}
    bt = M["bt"].astype(np.int64); hstart = (bt + 18000) // 3600 * 3600 - 18000
    usable = np.isin(hstart, list(good)) & ~np.load(f"{L.D}/mayhem.npy")
    day = ((bt - L.DAY0) // 86400).astype(int)
    N = len(M)
    # order within mint (all candidates, so k counts every earlier qualifying dump even in unusable hours)
    o = np.lexsort((M["cc"], M["mint"])); mint = M["mint"].astype(np.int64)
    k = np.zeros(N, int); prev = np.full(N, -1)
    ms = mint[o]; first = np.r_[True, ms[1:] != ms[:-1]]
    grp = np.cumsum(first) - 1; start = np.flatnonzero(first)
    k[o] = np.arange(N) - start[grp] + 1
    pv = np.r_[-1, o[:-1]]; pv[first] = -1; prev[o] = pv
    has = prev >= 0
    prev_exit = np.where(has, ES[np.maximum(prev, 0), 0] + 5, -1)
    prev_ok = has & (prev_exit < M["slot"])
    prev_pay = np.where(has, PN[np.maximum(prev, 0), 0, 0, 0], np.nan)
    gap = np.where(has, M["slot"] - M["slot"][np.maximum(prev, 0)], -1)
    # per-candidate values (exit 5 = HS index 0, fol 1.0 = index 0)
    ideal = np.where(FILL[:, 0], PN[:, 0, 0, 0], 0.0)
    rk = [2, 3, 4, 5]
    fr = FILL[:, rk].mean(1)
    ev = np.nanmean(np.where(FILL[:, rk], np.nan_to_num(PN[:, rk, 0, 0]), 0.0), axis=1)
    ev10 = np.nanmean(np.where(FILL[:, rk], np.nan_to_num(PN[:, rk, 0, 2]), 0.0), axis=1)
    valid = np.isfinite(PN[:, 0, 0, 0]) & usable
    cost_now = fr * NOWF + (1 - fr) * NOWX; cost_ch = fr * CHF + (1 - fr) * CHX
    cal = A_CAL * ev + B_CAL
    hq_open = X[:, feats.index("hq_open")] > 0
    # haqq's real lots per dump (code-matched), joined by the dump's (mint, slot, idx)
    B, LO, T = load()
    ids, idm = L.ids_map()
    key = {(int(m), int(s), int(i)): j for j, (m, s, i) in enumerate(zip(M["mint"], M["slot"], M["idx"]))}
    hq_net = np.zeros(N); hq_n = np.zeros(N, int)
    for l in LO:
        b = B[l["b"]]
        if b["d_slot"] is None or (b["d_slots"] or 9) > 2 or l["probe"]: continue
        j = key.get((idm[b["mint"]], b["d_slot"], b["d_idx"]))
        if j is None: continue
        hq_net[j] += l["cnet"]; hq_n[j] += 1
    np.savez(f"{OUT}/p5.npz", k=k, prev=prev, prev_ok=prev_ok, prev_pay=prev_pay, gap=gap, ideal=ideal, fr=fr, ev=ev, ev10=ev10, valid=valid,
             day=day, hq_net=hq_net, hq_n=hq_n, hq_open=hq_open)
    P(f"# Battlegrounds: k-th dump on a token (uni candidates {N:,}; usable non-mayhem with a valid 5-slot exit {int(valid.sum()):,})")
    P("Per-candidate mSOL: ideal = front-of-queue curve P&L; ours = expected curve P&L per attempt at our landing; net NOW/CHEAP = calibrated - tx costs;"
      " haqq = his real lots on that dump (code-matched, his costs), per lot.")

    def table(title, groups):
        P(f"\n## {title}")
        P("| group | dumps | ideal mean | ours mean | fill | calibrated net NOW | calibrated net CHEAP | -10% followers (ours, uncal.) | haqq lots | haqq mSOL/lot | haqq share of dumps bought |")
        P("|---|---|---|---|---|---|---|---|---|---|---|")
        for nm, m in groups:
            m = m & valid
            if m.sum() < 30: continue
            hl = hq_n[m].sum()
            P(f"| {nm} | {int(m.sum()):,} | {1000 * ideal[m].mean():+.2f} | {1000 * ev[m].mean():+.2f} | {100 * fr[m].mean():.0f}% | "
              f"{1000 * (cal[m] - cost_now[m]).mean():+.2f} | {1000 * (cal[m] - cost_ch[m]).mean():+.2f} | {1000 * ev10[m].mean():+.2f} | {hl:,} | "
              f"{1000 * hq_net[m].sum() / max(hl, 1):+.2f} | {100 * (hq_n[m] > 0).mean():.0f}% |")

    table("By k (k-th qualifying dump on the token), all days",
          [("k=1", k == 1), ("k=2", k == 2), ("k=3", k == 3), ("k=4-5", (k >= 4) & (k <= 5)), ("k=6-10", (k >= 6) & (k <= 10)), ("k=11+", k >= 11)])
    table("By the previous dump's ideal result (k >= 2, previous window closed; CAUSAL)",
          [("prev window still open (we'd hold)", has & ~prev_ok), ("prev paid < -5%", prev_ok & (prev_pay < -0.02)),
           ("prev -5..0%", prev_ok & (prev_pay >= -0.02) & (prev_pay < 0)), ("prev 0..+5%", prev_ok & (prev_pay >= 0) & (prev_pay < 0.02)),
           ("prev +5..+15%", prev_ok & (prev_pay >= 0.02) & (prev_pay < 0.06)), ("prev >= +15%", prev_ok & (prev_pay >= 0.06))])
    table("By slots since the previous qualifying dump (k >= 2)",
          [("0-5", has & (gap <= 5)), ("6-20", has & (gap > 5) & (gap <= 20)), ("21-100", has & (gap > 20) & (gap <= 100)), ("101-500", has & (gap > 100) & (gap <= 500)), ("> 500", has & (gap > 500))])
    table("haqq holding the token at the dump (public wallet; CAUSAL)", [("haqq holds", hq_open), ("haqq flat", ~hq_open)])
    table("k x prev result", [(f"k={a}-{b} prev>=+5%", (k >= a) & (k <= b) & prev_ok & (prev_pay >= 0.02)) for a, b in ((2, 2), (3, 5), (6, 999))] +
          [(f"k={a}-{b} prev<+5%", (k >= a) & (k <= b) & prev_ok & (prev_pay < 0.02)) for a, b in ((2, 2), (3, 5), (6, 999))])
    # per day for the main contrasts
    P("\n## Per day: calibrated net NOW per attempt (mSOL), k=1 vs k>=2 vs k>=2 & prev paid >= +5% (ideal)")
    P("| day | k=1 n / net | k>=2 n / net | k>=2 prev>=+5% n / net | k>=3 prev>=+5% n / net | haqq mSOL/lot k=1 / k>=2 / k>=2 prev>=+5% |")
    P("|---|---|---|---|---|---|")
    for d in range(7):
        dm = valid & (day == d)
        if dm.sum() < 100: continue
        def f(m):
            m = m & dm; return f"{int(m.sum()):,} / {1000 * (cal[m] - cost_now[m]).mean():+.2f}" if m.sum() else "-"
        def h(m):
            m = m & dm; return f"{1000 * hq_net[m].sum() / max(hq_n[m].sum(), 1):+.2f}"
        P(f"| {day_name(d)} | {f(k == 1)} | {f(k >= 2)} | {f((k >= 2) & prev_ok & (prev_pay >= 0.02))} | {f((k >= 3) & prev_ok & (prev_pay >= 0.02))} | "
          f"{h(k == 1)} / {h(k >= 2)} / {h((k >= 2) & prev_ok & (prev_pay >= 0.02))} |")
    P.save()


if __name__ == "__main__":
    main()
