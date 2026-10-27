#!/usr/bin/env python3
"""DV8 step 3a (read-only, offline): the dump universe on the whole tape (dv8/tab, 10-22 03:07 -> 10-28 01:12 PKT) with causal
features (same 28 as haqq_strat/s7) and OUR simulated outcome per landing model, exit and follower stress.
Tape: BOTH our wallets' rows removed (we are simulated, not replayed). haqq stays (a real competitor / follower).
Candidate (DV8 entry) = outside sell (not haqq) with single-trade drop >= 5%, sell >= 0.5 SOL, curve SOL after the sell > 30.52,
token age <= 30 min.
Landing models (where our buy lands in the chain order after the dump):
  ideal  : right after the dump (k = 0)
  ms     : s7 'real' = cc delay drawn from our measured first-copy delays (l2, all clients), independent of the dump
  rank   : contention-aware (c2): k = round(q * N_w), q drawn from the live P(q | N_w bucket); N_w = outside trades after the dump to
           the end of slot dump+1. DRAWS independent draws per candidate. MEASURED on 1,544 live fires.
  far leaders (dump slot leader not on the FRA near list): rank entry pushed FAR_MS later in chain-clock time (INFERRED from
           pre-send send->land medians, far - near = +30 ms).
Guard: fill if our entry tokens >= tokens at the post-dump curve / 1.05 (the engine's min_out; 99.7% agreement on live fires).
Exit: timer H slots after the entry slot (state after the last trade of slot entry+H); 'exact' follower model (later buys keep SOL,
later sells keep tokens; c1: matches realized fills +0.02 mSOL/fill); fol = share of outside buy SOL kept (1, .95, .90, .80).
A token with no trade after our entry exits at the state right after our buy (round-trip fees), not dropped (s7 dropped them).
P&L gross of tx costs at SIZE SOL, pump fee 1.25% per side.
Out: /home/moiz/sniper-data/dv8/uni.npz"""
import json, time, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L, dv8sim as S
FB = set(json.load(open("/home/moiz/sniper/ops/strategies/presend/filter/fbots_frozen.json")))
SIZE = 0.4; FEE = 0.0125; SMS = 212.0; DRAWS = 4; FAR_MS = 30.0
HS = (5, 8, 12, 30)
FOLS = (1.0, 0.95, 0.90, 0.80)
FEATS = ["drop", "sell_sol", "sell_pct", "vpost", "age_s", "n_tr", "n_wal", "nd_buy", "dev_sold", "d_dev", "d_bund", "d_early", "d_fb",
         "b10", "s10", "nb3", "ath_dd", "vs_launch", "last_dump_s", "n_dumps", "hq_prev", "hq_open", "fb_n", "bundle_sol", "dev_buy",
         "b30_ratio", "trades_10s", "hour"]
NB = None


def main():
    t0 = time.time()
    ids, idm = L.ids_map()
    h = idm[L.HAQQ]; our = [idm[w] for w in L.WAL.values() if w in idm]
    fb_ids = np.array(sorted(idm[w] for w in FB if w in idm), np.int64)
    T = np.load(f"{L.TAB}/trades.npy")
    T = T[~np.isin(T["user"], our)]
    o = np.argsort(T["mint"], kind="stable"); T = T[o]; del o
    sl = T["slot"].astype(np.int64); ix = T["idx"].astype(np.int64); us = T["user"].astype(np.int64); bu = T["buy"].astype(bool)
    so = T["sol"] / 1e9; tk = T["tok"].astype(np.float64); vs = T["vsol"] / 1e9; vt = T["vtok"].astype(np.float64); bt = T["bt"].astype(np.int64)
    mi_all = T["mint"]; del T
    ccg = L.cc(sl, ix)
    um, st_, = np.unique(mi_all, return_index=True); en_ = np.append(st_[1:], len(sl))
    CR = json.load(open(f"{L.TAB}/creates.json"))
    lm = json.load(open(f"{L.D}/landing_model.json")); ms_samp = np.array(lm["near"]["all"])
    rk = json.load(open(f"{L.D}/rank_model.json")); edges = np.array(rk["edges"]); rq = {int(k): np.array(v) for k, v in rk["q"].items()}
    print(f"tape {len(sl):,} rows (ours removed), {len(um):,} mints ({time.time() - t0:.0f}s)", flush=True)
    rng = np.random.default_rng(7)
    X = []; META = []
    for mi, a, e in zip(um.tolist(), st_.tolist(), en_.tolist()):
        c = CR.get(ids[mi])
        if not c or c.get("slot") is None or e - a < 8: continue
        cs = int(c["slot"]); cr = idm.get(c.get("creator"), -2)
        s_ = sl[a:e]; u_ = us[a:e]; b_ = bu[a:e]; o_ = so[a:e]; k_ = tk[a:e]; v_ = vs[a:e]; w_ = vt[a:e]; t_ = bt[a:e]
        n = e - a
        px = v_ / np.maximum(w_, 1)
        v_c = float(c.get("vsol") or 30e9) / 1e9; t_c = float(c.get("vtok") or 1.073e15)
        pxp = np.empty(n); pxp[0] = v_c / t_c; pxp[1:] = px[:-1]
        with np.errstate(divide="ignore", invalid="ignore"): drop = np.where(~b_, 1 - px / pxp, 0.0)
        ishq = u_ == h; outside = ~ishq
        cand = np.flatnonzero(outside & ~b_ & (drop >= 0.05) & (o_ >= 0.5) & (v_ > 30.52) & ((s_ - cs) * 0.212 <= 1800))
        if not len(cand): continue
        bsol = np.where(b_ & outside, o_, 0.0); ssol = np.where(~b_ & outside, o_, 0.0)
        cb = np.cumsum(bsol); cs_ = np.cumsum(ssol)
        nd = np.where(b_ & outside & (u_ != cr), o_, 0.0); cnd = np.cumsum(nd)
        devs = np.cumsum(~b_ & (u_ == cr)); devb = np.cumsum(np.where(b_ & (u_ == cr), o_, 0.0))
        _, first_idx = np.unique(u_, return_index=True); firstseen = np.zeros(n, bool); firstseen[first_idx] = True
        cw = np.cumsum(firstseen)
        isfb = np.isin(u_, fb_ids); cfb = np.cumsum(firstseen & isfb)
        ath = np.maximum.accumulate(px)
        bund = set(u_[(s_ == cs) & b_].tolist()); early = set(u_[(s_ <= cs + 10) & b_].tolist())
        bundle_sol = float(o_[(s_ == cs) & b_ & (u_ != cr)].sum())
        chq = np.cumsum(ishq); hq_bal = np.cumsum(np.where(ishq, np.where(b_, k_, -k_), 0.0))
        dumpk = np.flatnonzero(outside & ~b_ & (drop >= 0.05))
        for j in cand.tolist():
            lo10 = int(np.searchsorted(s_, s_[j] - 47)); lo3 = int(np.searchsorted(s_, s_[j] - 3)); lo30 = int(np.searchsorted(s_, s_[j] - 141))
            pdk = dumpk[dumpk < j]; seller = int(u_[j])
            b10 = cb[j] - (cb[lo10 - 1] if lo10 > 0 else 0); s10 = cs_[j] - (cs_[lo10 - 1] if lo10 > 0 else 0)
            b30 = cb[j] - (cb[lo30 - 1] if lo30 > 0 else 0)
            f = [drop[j], o_[j], k_[j] / 1e13, v_[j], (s_[j] - cs) * 0.212, j, cw[j], cnd[j], float(devs[j] > 0), float(seller == cr),
                 float(seller in bund), float(seller in early), float(isfb[j]), b10, s10, float((b_[lo3:j] & outside[lo3:j]).sum()),
                 1 - px[j] / ath[j], v_[j] / v_c, ((s_[j] - s_[pdk[-1]]) * 0.212 if len(pdk) else 999.0), float(len(pdk)),
                 float(chq[j]), float(hq_bal[j] > 1e6), float(cfb[j]), bundle_sol, float(devb[j]), b10 / max(b30, 1e-3),
                 float(j - lo10), float(time.gmtime(int(t_[j]) + 18000).tm_hour)]
            nxt = dumpk[dumpk > j]; lim = int(nxt[0]) if len(nxt) else n
            hi2 = min(int(np.searchsorted(s_, s_[j] + 2, side="right")), lim)
            hq = bool((ishq[j + 1:hi2] & b_[j + 1:hi2]).any())
            nw = int(np.searchsorted(s_, s_[j] + 1, side="right")) - j - 1
            X.append(f); META.append((mi, a + j, int(s_[j]), int(ix[a + j]), int(t_[j]), hq, ccg[a + j], int(s_[j] - cs), nw, e))
        if len(META) % 100000 < len(cand):
            print(f"  {len(META):,} candidates ({time.time() - t0:.0f}s)", flush=True)
    X = np.array(X, np.float32)
    M = np.array(META, dtype=[("mint", "u4"), ("row", "i8"), ("slot", "i8"), ("idx", "u4"), ("bt", "i8"), ("hq", "?"), ("cc", "f8"), ("age", "i8"),
                              ("nw", "i4"), ("end", "i8")])
    N = len(M); print(f"{N:,} candidates; features done ({time.time() - t0:.0f}s)", flush=True)
    # leader of the dump slot (FRA near list); epoch 1064 unknown -> treated as near
    lead_cache = {}
    near = np.ones(N, bool); lcls = np.empty(N, "U8")
    for i, s in enumerate(M["slot"].tolist()):
        v = lead_cache.get(s)
        if v is None: v = lead_cache[s] = L.leader_info(s, "FRA")[1:]
        lcls[i] = v[0]; near[i] = v[1] is not False
    # ---- entries per landing model: columns = ideal, ms, rank x DRAWS
    jd = M["row"]; endm = M["end"]
    names = ["ideal", "ms"] + [f"rank{d}" for d in range(DRAWS)]
    R = np.zeros((N, len(names)), np.int64); ES = np.zeros((N, len(names)), np.int64)
    R[:, 0] = jd + 1; ES[:, 0] = M["slot"]
    Lms = ms_samp[rng.integers(0, len(ms_samp), N)]
    R[:, 1] = np.maximum(np.searchsorted(ccg, M["cc"] + Lms, side="right"), jd + 1)
    ES[:, 1] = np.maximum(M["slot"], ((M["cc"] + Lms) // SMS).astype(np.int64))
    bk = np.clip(np.searchsorted(edges, M["nw"], side="right") - 1, 0, len(edges) - 2)
    for d in range(DRAWS):
        qd = np.zeros(N)
        for b in np.unique(bk):
            m = bk == b; qs = rq[int(b)] if int(b) in rq else rq[max(rq)]
            qd[m] = qs[rng.integers(0, len(qs), m.sum())]
        k = np.where(M["nw"] > 0, np.round(qd * M["nw"]), qd).astype(np.int64)
        r = jd + 1 + k
        # far leader: land FAR_MS (chain clock) later than the near-model position (INFERRED)
        base_cc = np.where(k > 0, ccg[np.minimum(r - 1, len(ccg) - 1)], M["cc"])
        rf = np.maximum(np.searchsorted(ccg, base_cc + FAR_MS, side="right"), r)
        r = np.where(near, r, rf)
        R[:, 2 + d] = r
        ES[:, 2 + d] = np.where(r - 1 > jd, sl[np.minimum(r - 1, len(sl) - 1)], M["slot"])
    # beyond the mint's last row: entry after the last trade (state of the last row)
    R = np.minimum(R, endm[:, None])
    # ---- guard (tokens vs post-dump / 1.05) and entry price ratio
    def etok(rr):
        v0 = vs[rr - 1]; t0_ = vt[rr - 1]; return t0_ - v0 * t0_ / (v0 + SIZE / (1 + FEE))
    tokd = etok(jd + 1)
    FILL = np.zeros((N, len(names)), bool); PR = np.zeros((N, len(names)), np.float32)
    for c in range(len(names)):
        te_ = etok(R[:, c]); FILL[:, c] = te_ >= tokd / 1.05; PR[:, c] = tokd / np.maximum(te_, 1)
    # ---- exits: q_H = last row of the mint with slot <= es + H (>= r-1)
    tape_end_slot = int(sl.max())
    Q = np.zeros((N, len(names), len(HS)), np.int64); VALID = np.zeros((N, len(names), len(HS)), bool)
    for c in range(len(names)):
        for hi, H in enumerate(HS):
            tgt = ES[:, c] + H
            # search within each mint's span: global searchsorted on (mint, slot) via composite key
            Q[:, c, hi] = np.maximum(_search_mint(sl, M["row"], endm, tgt), R[:, c] - 1)
            VALID[:, c, hi] = tgt <= tape_end_slot - 2
    print(f"entries/exits done ({time.time() - t0:.0f}s)", flush=True)
    # ---- exact sequential sim, vectorised across (candidate, model) pairs, all fol levels and exits at once
    PN = np.full((N, len(names), len(HS), len(FOLS)), np.nan, np.float32)
    ci, mj = np.nonzero(FILL)
    r0 = R[ci, mj]; qq = Q[ci, mj, :]
    v0 = vs[r0 - 1]; t0_ = vt[r0 - 1]; K = v0 * t0_
    sn = SIZE / (1 + FEE); V = np.repeat((v0 + sn)[:, None], len(FOLS), 1); Tt = K[:, None] / V; tok = (t0_ - K / (v0 + sn))
    out = np.zeros((len(ci), len(HS), len(FOLS)))
    def proceeds(V, Tt): return (V - K[:, None] / (Tt + tok[:, None])) * (1 - FEE) - SIZE
    p0 = proceeds(V, Tt)
    for hi in range(len(HS)): out[:, hi, :] = p0
    ln = qq[:, -1] - r0 + 1                     # steps needed for the longest exit
    order = np.argsort(-ln); ln_s = ln[order]
    r0s = r0[order]; qqs = qq[order]; V = V[order]; Tt = Tt[order]; Ks = K[order]; toks = tok[order]
    fol = np.array(FOLS)[None, :]
    m = 0; nact = int((ln_s > 0).sum())
    outs = out[order]
    while nact > 0:
        idx = r0s[:nact] + m
        b = bu[idx]; s = so[idx]; tkk = tk[idx]
        Vb = V[:nact] + s[:, None] * fol; Ts = Tt[:nact] + tkk[:, None]
        V[:nact] = np.where(b[:, None], Vb, Ks[:nact, None] / Ts)
        Tt[:nact] = np.where(b[:, None], Ks[:nact, None] / Vb, Ts)
        for hi in range(len(HS)):
            hit = idx == qqs[:nact, hi]
            if hit.any():
                hv = np.flatnonzero(hit)
                outs[hv, hi, :] = (V[hv] - Ks[hv, None] / (Tt[hv] + toks[hv, None])) * (1 - FEE) - SIZE
        m += 1
        while nact > 0 and ln_s[nact - 1] <= m: nact -= 1
        if m % 200 == 0: print(f"   sim step {m}, active {nact:,} ({time.time() - t0:.0f}s)", flush=True)
    out = np.empty_like(outs); out[order] = outs
    PN[ci, mj] = out.astype(np.float32)
    PN[~np.broadcast_to(VALID[..., None], PN.shape)] = np.nan
    # vshift (s7) for the ms model, fol=1, for the comparison with the earlier DV8 replay
    VS7 = np.full((N, len(HS)), np.nan, np.float32)
    rr = R[:, 1]; v0 = vs[rr - 1]; t0_ = vt[rr - 1]; K = v0 * t0_; v1 = v0 + sn; tk7 = t0_ - K / v1
    for hi in range(len(HS)):
        q = Q[:, 1, hi]; Vq = v1 + (vs[q] - v0); VS7[:, hi] = np.where(FILL[:, 1] & VALID[:, 1, hi], (Vq - K / (K / Vq + tk7)) * (1 - FEE) - SIZE, np.nan)
    np.savez(f"{L.D}/uni.npz", X=X, M=M, feats=np.array(FEATS), names=np.array(names), HS=np.array(HS), FOLS=np.array(FOLS),
             FILL=FILL, PR=PR, PN=PN, VS7=VS7, near=near, lcls=lcls, LASTSL=sl[M['end'] - 1], R=R.astype(np.int64), ES=ES)
    print(f"done: {N:,} candidates; fill rate ideal {FILL[:, 0].mean():.3f} ms {FILL[:, 1].mean():.3f} rank {FILL[:, 2:].mean():.3f}; "
          f"far share {1 - near.mean():.3f} ({time.time() - t0:.0f}s)", flush=True)


def _search_mint(sl, row, endm, tgt):
    """for each candidate: last global row index in [row, end) with slot <= tgt (rows of one mint are slot-sorted)"""
    out = np.empty(len(row), np.int64)
    # binary search per candidate, vectorised: lo=row, hi=end
    lo = row.copy(); hi = endm.copy()
    while True:
        act = lo < hi
        if not act.any(): break
        mid = (lo + hi) // 2
        go = act & (sl[np.minimum(mid, len(sl) - 1)] <= tgt)
        lo = np.where(go, mid + 1, lo); hi = np.where(act & ~go, mid, hi)
    return lo - 1


if __name__ == "__main__":
    main()
