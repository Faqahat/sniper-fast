#!/usr/bin/env python3
"""BOTREG step 1 [MEASURED]: per completed PKT hour, per wallet behaviour counters -> /home/it/sniper-data/botreg/hourly/<hour>.npz
Uses only chunks up to the end of that hour (+60 s for the 2-slot follow window), plus a 6 h look-back for trip opens.
Definitions (explicit thresholds):
  DUMP      = outside sell with SOL >= 1.0, or >= 2% of supply with SOL >= 0.3 (not our wallets)
  DIP BUY   = buy on the same mint <= 2 slots after a DUMP (after it in block order), buyer != dumper
  FOLLOW    = buy on the same mint <= 2 slots after one of OUR buys (after it in block order), buyer not ours
  TRIP      = per (wallet, mint): from the first buy until the wallet's net tokens fall to <= 1% of the tokens it bought on
              that mint in the window; P&L = sells - buys - 1.25%/side pump fee (no network fee / tips: recordings lack the split)
              trips that sell more than they bought in the window (open before the look-back) are dropped
  FAIL BUY  = failed tx with a pump.fun Buy instruction (payer = first signer); DIP FAIL = <= 2 slots after a DUMP on that mint
Row kept if the wallet bought >= 2 times, or had a dip buy / follow / failed buy in the hour.
usage: x1_hourly.py [--redo]   env NW workers (default 3)"""
import sys, os, time, pickle
import numpy as np
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

OUT = f"{C.DATA}/hourly"
LB = 6 * C.H
HB = np.array([2, 10, 50, 150, 600])            # hold-slot histogram edges (bins: <=2, <=10, <=50, <=150, <=600, >600)
OURS = np.array(sorted(C.OURS64), dtype=np.uint64)


def seg_last(flag, M):
    """for each row i: index of the last row j < i with flag[j] on the same mint (rows mint-sorted), else -1"""
    n = len(flag)
    v = np.where(flag, np.arange(n), -1)
    acc = np.maximum.accumulate(v)
    last = np.r_[-1, acc[:-1]]
    ok = last >= 0
    ok[ok] = M[last[ok]] == M[ok.nonzero()[0]]
    return np.where(ok, last, -1)


def agg_hour(h, idx=None):
    w = C.load_window(h - LB, h + C.H + 60, idx)
    if w is None: return None
    T, F = w
    S, M, U, B = T["slot"], T["mint"], T["user"], T["buy"]
    SOL, TOK, BT = T["sol"].astype(np.float64), T["tok"].astype(np.float64), T["bt"]
    n = len(S)
    ours = np.isin(U, OURS)
    inh = (BT >= h) & (BT < h + C.H)
    # dumps and dip buys
    dump = (B == 0) & ~ours & ((SOL >= 1e9) | ((TOK >= 0.02 * C.SUP) & (SOL >= 0.3e9)))
    ld = seg_last(dump, M)
    hasd = ld >= 0
    dip = (B == 1) & hasd
    dip[hasd] &= (S[hasd] - S[ld[hasd]] <= 2) & (U[hasd] != U[ld[hasd]])
    # follows after our buys
    ob = ours & (B == 1)
    lo = seg_last(ob, M)
    haso = lo >= 0
    fol = (B == 1) & haso & ~ours
    fol[haso] &= (S[haso] - S[lo[haso]] <= 2)
    # trips: order rows by (user, mint, time) — mint-sorted order already is time order within a mint
    o = np.lexsort((np.arange(n), M, U))
    Uo, Mo, Bo, So, BTo = U[o], M[o], B[o], S[o], BT[o]
    sg = np.where(Bo == 1, TOK[o], -TOK[o]); cash = np.where(Bo == 1, -SOL[o], SOL[o]) - 0.0125 * SOL[o]
    btok = np.where(Bo == 1, TOK[o], 0.0)
    gst = np.r_[True, (Uo[1:] != Uo[:-1]) | (Mo[1:] != Mo[:-1])]
    gidx = np.cumsum(gst) - 1
    starts = np.nonzero(gst)[0]
    def gcum(x):
        c = np.cumsum(x); base = np.r_[0.0, c][starts]
        return c - base[gidx]
    pos = gcum(sg); cb = gcum(btok)
    close = (Bo == 0) & (cb > 0) & (pos <= 0.01 * cb)
    # trips = segments between group starts and the row after each close
    segst = np.unique(np.r_[starts, np.nonzero(close)[0] + 1])
    segst = segst[segst < n]
    seg_end = np.r_[segst[1:], n] - 1
    closed = close[seg_end]
    pnl = np.add.reduceat(cash, segst); bsol = np.add.reduceat(np.where(Bo == 1, SOL[o], 0.0), segst)
    # validity: a segment must start with a buy and never go below -1% of its own bought tokens
    first_buy = Bo[segst] == 1
    segpos = np.add.reduceat(sg, segst)          # final net of the segment
    segb = np.add.reduceat(btok, segst)
    valid = closed & first_buy & (segb > 0) & (segpos >= -0.01 * segb)
    hold = So[seg_end] - So[segst]
    tin = valid & (BTo[seg_end] >= h) & (BTo[seg_end] < h + C.H)
    tu = Uo[seg_end][tin]; tp = pnl[tin]; th = hold[tin]; tbs = bsol[tin]
    # failed buys in the hour
    finh = (F["bt"] >= h) & (F["bt"] < h + C.H) & (F["kind"] == 1)
    fM, fS, fP = F["mint"][finh], F["slot"][finh], F["payer"][finh]
    # dip fails: a dump on the same mint at slot in [fS-2, fS]
    dM, dS = M[dump], S[dump]
    if len(dM) and len(fM):
        um, inv = np.unique(np.r_[dM, fM], return_inverse=True)
        kd = inv[:len(dM)].astype(np.int64) * (1 << 34) + dS; kf = inv[len(dM):].astype(np.int64) * (1 << 34) + fS
        kd.sort()
        j = np.searchsorted(kd, kf, side="right") - 1
        fdip = (j >= 0) & (kf - kd[np.maximum(j, 0)] <= 2) & (kd[np.maximum(j, 0)] >> 34 == kf >> 34)
    else:
        fdip = np.zeros(len(fM), bool)
    # ---- per-wallet aggregation ----
    bm = inh & (B == 1); sm = inh & (B == 0)
    allu = np.unique(np.r_[U[inh], tu, fP])
    def cnt(keys, wts=None):
        i = np.searchsorted(allu, keys)
        return np.bincount(i, weights=wts, minlength=len(allu))
    R = {"u": allu}
    R["n_buy"] = cnt(U[bm]); R["buy_sol"] = cnt(U[bm], SOL[bm])
    R["n_sell"] = cnt(U[sm])
    R["n_dip"] = cnt(U[bm & dip]); R["dip_sol"] = cnt(U[bm & dip], SOL[bm & dip])
    R["n_fol"] = cnt(U[bm & fol])
    # distinct our-fills followed per wallet
    fr = np.nonzero(bm & fol)[0]
    pr = np.unique(np.stack([U[fr], lo[fr].astype(np.uint64)], 1), axis=0) if len(fr) else np.zeros((0, 2), np.uint64)
    R["n_fol_fills"] = cnt(pr[:, 0]) if len(pr) else np.zeros(len(allu))
    R["n_trip"] = cnt(tu); R["pnl"] = cnt(tu, tp); R["n_win"] = cnt(tu[tp > 0]); R["trip_bsol"] = cnt(tu, tbs)
    hb = np.searchsorted(HB, th, side="left")       # 0..5
    for k in range(6): R[f"hold{k}"] = cnt(tu[hb == k])
    R["n_fail"] = cnt(fP); R["n_fail_dip"] = cnt(fP[fdip])
    ui = np.searchsorted(allu, U[inh])
    first = np.full(len(allu), np.iinfo(np.int64).max); last = np.zeros(len(allu), np.int64)
    np.minimum.at(first, ui, BT[inh]); np.maximum.at(last, ui, BT[inh])
    R["first_bt"] = first; R["last_bt"] = last
    keep = (R["n_buy"] >= 2) | (R["n_dip"] > 0) | (R["n_fol"] > 0) | (R["n_fail"] > 0) | (R["n_trip"] >= 2)
    R = {k: (v[keep].astype(np.float32) if v.dtype == np.float64 else v[keep]) for k, v in R.items()}
    # ---- our positions in the hour (for the SELLS-INTO-US class): per our buy row -> our next sell on that mint,
    # outside sells in between (sold into our hold), the trigger dumper (DUMP <= 2 slots before), holders >= 0.5% at our buy
    P = []
    for k in np.nonzero(bm & ours)[0]:
        g0 = np.searchsorted(M, M[k]); g1 = np.searchsorted(M, M[k], side="right")
        nxt = np.nonzero((U[k + 1:g1] == U[k]) & (B[k + 1:g1] == 0))[0]
        if not len(nxt): continue
        j = k + 1 + int(nxt[0])
        if S[j] - S[k] > 30: continue
        frac = min(1.0, TOK[k] / max(TOK[j], 1.0))
        pnl = SOL[j] * frac - SOL[k] - 0.0125 * (SOL[j] * frac + SOL[k])
        mid = np.arange(k + 1, j)
        sel = mid[(B[mid] == 0) & ~ours[mid]]
        sellers = [(int(U[i]), float(SOL[i] / 1e9), float(TOK[i] / C.SUP * 100)) for i in sel]
        pr = np.arange(g0, k)
        hold = []
        if len(pr):
            uu, iv = np.unique(U[pr], return_inverse=True)
            net = np.bincount(iv, weights=np.where(B[pr] == 1, TOK[pr], -TOK[pr])) / C.SUP * 100
            for x in np.nonzero(net >= 0.5)[0]:
                if int(uu[x]) not in C.OURS64: hold.append((int(uu[x]), float(net[x])))
        d = ld[k]
        trig = (int(U[d]), float(SOL[d] / 1e9), float(TOK[d] / C.SUP * 100)) if d >= 0 and S[k] - S[d] <= 2 else None
        # trades in the 60 slots before our buy (for the bait rule) and token age (censored at the 6 h look-back)
        pw = pr[S[pr] >= S[k] - 60] if len(pr) else pr
        pre = [(int(U[i]), int(B[i]), float(TOK[i] / C.SUP * 100), float(SOL[i] / 1e9), int(S[i])) for i in pw if not ours[i]]
        P.append({"bt": int(BT[k]), "slot": int(S[k]), "mint": int(M[k]), "w": int(U[k]), "buy_sol": float(SOL[k] / 1e9),
                  "pnl": float(pnl / 1e9), "sellers": sellers, "holders": hold, "trig": trig, "pre": pre,
                  "age": int(S[k] - S[g0]), "age_cens": bool(BT[g0] <= h - LB + 600)})
    G = {"g_our_fills": int((bm & ours).sum()), "g_dumps": int((inh & dump).sum()), "g_trades": int(inh.sum()),
         "g_dip_sol": float(SOL[bm & dip].sum()), "g_dip_n": int((bm & dip).sum()), "g_fails": int(finh.sum())}
    return R, G, P


def work(h):
    out = f"{OUT}/{h}.npz"
    if os.path.exists(out) and os.path.exists(f"{OUT}/{h}.ours.pkl"): return h, -1
    r = agg_hour(h, IDX)
    if r is None: return h, 0
    R, G, P = r
    pickle.dump(P, open(f"{OUT}/{h}.ours.pkl", "wb"))
    np.savez(out + ".tmp.npz", **R, **{k: np.array(v) for k, v in G.items()})
    os.rename(out + ".tmp.npz", out)
    return h, len(R["u"])


IDX = None
if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    IDX = C.chunk_index()
    hrs = C.covered_hours(IDX)
    last_chunk = max(IDX)
    hrs = [h for h in hrs if h + C.H + 60 <= last_chunk]          # hour complete (its follow window recorded)
    print("hours", len(hrs), C.pkt(hrs[0]), "->", C.pkt(hrs[-1]), flush=True)
    t0 = time.time()
    with Pool(int(os.environ.get("NW", "3"))) as p:
        for k, (h, nr) in enumerate(p.imap(work, hrs)):
            if nr >= 0: print(C.pkt(h), nr, round(time.time() - t0), flush=True)
    print("done", flush=True)
