#!/usr/bin/env python3
"""9pQQ exact-rules, step 1: decision moments with rich state, for BUY (9pQQ flat) and SELL (9pQQ holds) decisions.
One row per OUTSIDE landed curve trade on a token launched inside the recording. Vectorised, read-only on the tape.
Labels: yb_imm (this row is the last outside trade before its buy, buy <= 1 slot later), yb_any (it buys this mint at a later row
in slot s or s+1), ys_imm / ys_any (same for its sell, only while it holds).
-> /home/moiz/sniper-data/rivals/9pQQ/exact/dm_<run>.npz (float32 features + int labels + s, m, u, row).  usage: dm_build.py [run ...]"""
import sys
import numpy as np
import xlib as X, tlib9 as L

def seg_ffill(mask, seg0):
    """index of the latest row <= j (same mint) where mask is true, else -1"""
    idx = np.where(mask, np.arange(len(mask)), -1)
    f = np.maximum.accumulate(idx)
    return np.where(f >= seg0, f, -1)

def build(run):
    t = X.load(run); la = L.launches(run)
    n = t.n; idx = np.arange(n); own = t.own; oth = ~own
    s0 = int(t.s.min()); key = (t.m.astype(np.int64) << 32) | (t.s - s0)
    F = {}
    v_post = L.vsol(t.cpost.astype(np.float64)) / 1e9; v_pre = L.vsol(t.cpre.astype(np.float64)) / 1e9
    size = np.abs(t.sol) / 1e9; side = np.sign(t.tok)
    F["side"] = side; F["size"] = size; F["vsol"] = v_post; F["vpre"] = v_pre
    F["impact"] = v_post / v_pre - 1
    ucnt = np.bincount(t.u, minlength=len(t.users)); F["trader_cnt"] = ucnt[t.u].astype(float)
    # token facts
    lslot = np.array([la[m]["slot"] if m in la else -1 for m in t.mints], np.int64)
    lbt = np.array([la[m]["bt"] if m in la else -1 for m in t.mints], np.int64)
    may = np.array([la[m]["may"] if m in la else False for m in t.mints], bool)
    crt = np.array([t.user_ix.get(la[m]["creator"], -2) if m in la else -2 for m in t.mints], np.int64)
    F["age"] = (t.s - lslot[t.m]).astype(float); F["age_bt"] = (t.bt - lbt[t.m]).astype(float); F["may"] = may[t.m].astype(float)
    F["is_creator"] = (t.u == crt[t.m]).astype(float)
    first = t.mstart[:-1]
    devbuy = np.where((t.u[np.minimum(first, n - 1)] == crt) & (t.tok[np.minimum(first, n - 1)] > 0), np.abs(t.sol[np.minimum(first, n - 1)]) / 1e9, 0.0)
    F["dev_buy"] = devbuy[t.m]
    dsell = (t.u == crt[t.m]) & (t.tok < 0)
    F["dev_sold"] = (seg_ffill(dsell, t.seg0) >= 0).astype(float)
    F["ntr_sofar"] = (idx - t.seg0).astype(float)
    # ATH / ATL of curve so far (incl. this row)
    off = t.m.astype(np.float64) * 1e4
    ath = np.maximum.accumulate(v_post + off) - off
    F["ath"] = ath; F["dd_ath"] = v_post / ath - 1
    # window flows by others
    sg = np.where(oth, -t.sol, 0) / 1e9                      # + = SOL into curve
    bsol = np.where(oth & (t.tok > 0), size, 0.0); ssol = np.where(oth & (t.tok < 0), size, 0.0)
    nb = (oth & (t.tok > 0)).astype(float); ns = (oth & (t.tok < 0)).astype(float)
    big = (oth & (size >= 0.05)).astype(float)
    C = {k: np.concatenate([[0.0], np.cumsum(v)]) for k, v in dict(sg=sg, bsol=bsol, ssol=ssol, nb=nb, ns=ns, big=big).items()}
    for w in (0, 1, 3, 10, 30, 100):
        lo = np.searchsorted(key, key - w, "left")
        for k in ("sg", "bsol", "ssol", "nb", "ns"):
            F[f"{k}{w}"] = C[k][idx + 1] - C[k][lo]
        if w in (3, 30): F[f"big{w}"] = C["big"][idx + 1] - C["big"][lo]
        F[f"dv{w}"] = v_post / v_pre[lo] - 1                   # curve SOL change over the window (from before its first trade)
    # in-slot position
    lo0 = np.searchsorted(key, key, "left"); F["slot_pos"] = (idx - lo0).astype(float)
    # last outside buy / sell (before this row, same mint)
    lb = seg_ffill(oth & (t.tok > 0), t.seg0); lsl = seg_ffill(oth & (t.tok < 0), t.seg0)
    pl = np.concatenate([[-1], lb[:-1]]); pl = np.where(pl >= t.seg0, pl, -1)
    F["since_obuy"] = np.where(pl >= 0, t.s - t.s[np.maximum(pl, 0)], 9999).astype(float)
    pl = np.concatenate([[-1], lsl[:-1]]); pl = np.where(pl >= t.seg0, pl, -1)
    F["since_osell"] = np.where(pl >= 0, t.s - t.s[np.maximum(pl, 0)], 9999).astype(float)
    pr = np.concatenate([[-1], idx[:-1]]); pr = np.where(pr >= t.seg0, pr, -1)
    F["since_prev"] = np.where(pr >= 0, t.s - t.s[np.maximum(pr, 0)], 9999).astype(float)
    # own history on this mint
    ob = own & (t.tok > 0); osl = own & (t.tok < 0)
    lob = seg_ffill(ob, t.seg0); los = seg_ffill(osl, t.seg0)
    nsell_m = np.concatenate([[0], np.cumsum(osl)]); F["k_done"] = (nsell_m[idx + 1] - nsell_m[t.seg0]).astype(float)
    F["since_own_sell"] = np.where(los >= 0, t.s - t.s[np.maximum(los, 0)], 99999).astype(float)
    F["since_own_buy"] = np.where(lob >= 0, t.s - t.s[np.maximum(lob, 0)], 99999).astype(float)
    vb = v_post[np.maximum(lob, 0)]; vs_ = v_pre[np.maximum(los, 0)]
    F["v_vs_ownbuy"] = np.where(lob >= 0, v_post / vb - 1, np.nan)             # in hold = its curve-SOL return proxy
    F["v_vs_ownsell"] = np.where(los >= 0, v_post / vs_ - 1, np.nan)
    # last closed trip return (price at its sell / price after its buy)
    P = L.price(t.cpost.astype(np.float64)); Pp = L.price(t.cpre.astype(np.float64))
    lob_before_sell = np.where(los >= 0, lob[np.maximum(los, 0) - 1 if True else 0], -1)
    lob_before_sell = np.where((los > 0) & (lob_before_sell >= t.seg0), lob_before_sell, -1)
    F["last_trip_ret"] = np.where((los >= 0) & (lob_before_sell >= 0), Pp[np.maximum(los, 0)] / P[np.maximum(lob_before_sell, 0)] - 1, np.nan)
    # hold-specific: peak since entry, outside flow since entry, return
    gid = np.cumsum(ob) + t.m.astype(np.int64) * 0   # own buy count increments (global); combine with mint via offset below
    goff = (np.cumsum(ob) * 2 + t.m * 0).astype(np.float64)
    # group id unique per (mint, trip): segment changes when mint changes or own buy happens
    newg = np.r_[True, t.m[1:] != t.m[:-1]] | ob
    g = np.cumsum(newg).astype(np.float64) * 1e4
    F["peak_since_buy"] = np.maximum.accumulate(v_post + g) - g
    F["trough_since_buy"] = -(np.maximum.accumulate(-v_post + g) - g)
    F["dd_peak_buy"] = v_post / F["peak_since_buy"] - 1
    for k in ("sg", "bsol", "ssol", "nb", "ns"):
        base = C[k][np.maximum(lob, 0) + 1]
        F[f"{k}_hold"] = np.where(lob >= 0, C[k][idx + 1] - base, np.nan)
    # global own state: open positions and recent own buy rate at this row
    oe = np.where(own)[0]; ok_ = t.s[oe] * 10000 + t.i[oe]; o_ = np.argsort(ok_, kind="stable"); oe = oe[o_]; ok_ = ok_[o_]
    delta = np.where(t.tok[oe] > 0, 1, -1); cdel = np.concatenate([[0], np.cumsum(delta)])
    rk = t.s * 10000 + t.i
    F["open_pos"] = cdel[np.searchsorted(ok_, rk, "left")].astype(float)
    obk = np.sort(t.s[t.ob]); F["own_buys25"] = (np.searchsorted(obk, t.s, "left") - np.searchsorted(obk, t.s - 25, "left")).astype(float)
    F["hour"] = ((t.bt // 3600 + 5) % 24).astype(float)
    # labels
    nxt_own = np.where(own, idx, n); nxt_own = np.minimum.accumulate(nxt_own[::-1])[::-1]
    nxt = np.concatenate([nxt_own[1:], [n]])                     # next own row strictly after j
    nxt_ok = (nxt < n)
    nxt_c = np.minimum(nxt, n - 1)
    same = nxt_ok & (t.m[nxt_c] == t.m) & (t.s[nxt_c] - t.s <= 1)
    nb_ = same & (t.tok[nxt_c] > 0); ns_ = same & (t.tok[nxt_c] < 0)
    yb_imm = t.trig_b.copy(); ys_imm = t.trig_s.copy()
    yb_any = nb_ & ~t.hold; ys_any = ns_ & t.hold
    keep = oth & (lslot[t.m] >= 0)
    out = {k: np.asarray(v, dtype=np.float32)[keep] for k, v in F.items()}
    out.update(yb_imm=yb_imm[keep], yb_any=yb_any[keep], ys_imm=ys_imm[keep], ys_any=ys_any[keep], hold=t.hold[keep],
               s=t.s[keep], i=t.i[keep], m=t.m[keep], u=t.u[keep], row=idx[keep])
    np.savez(f"{X.XOUT}/dm_{run}.npz", **out)
    print(run, "rows", int(keep.sum()), "flat", int((~t.hold[keep]).sum()), "yb_imm", int(yb_imm[keep].sum()), "yb_any", int(yb_any[keep].sum()),
          "ys_imm", int(ys_imm[keep].sum()), "ys_any", int(ys_any[keep].sum()), "own buys", len(t.ob), flush=True)

if __name__ == "__main__":
    for r in (sys.argv[1:] or X.RUNS): build(r)
