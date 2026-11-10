#!/usr/bin/env python3
"""FLATPERFECT step 1 [MEASURED, causal features from the recorded chain]: per live position (T2 or re-arm) ->
  A) at TRIGGER (rows strictly before the trigger row in chain order, global state with slot < trigger slot - 2 for closed windows):
     token state, holder concentration, named/cohort bot presence + warmth, whale history (hold clock), creator history,
     market follower regime (share of big dumps chain-wide that drew cohort/named buys within 2 slots, last 1/5/30 min).
  B) PRE-FILL (monotone counts over rows after the trigger and with slot <= fill slot - 2: still knowable before our landing try was sent)
  C) POST (labels only, never features): cohort/named buys within 2 slots after our fill, dumper identity.
Input positions: a pickle list of dicts with mint, kind, trig_slot, trig_idx, buy_slot, buy_idx, whale, key (any id).
usage: fp1_chain.py POS.pkl OUT.pkl"""
import numpy as np, pickle, json, sys, os, collections
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/flatsig")
import flib as L

D = os.environ.get("CHAIN_DIR", L.D)      # chain.npz / fails.npz / spans.json (default: the flatsig chain); cohort always from flatsig
SUP = 1e15
z = np.load(f"{D}/chain.npz")
S, I, M, U, B = z["slot"], z["idx"], z["mint"], z["user"], z["buy"]
SOL, TOK, VS = z["sol"].astype(np.float64), z["tok"].astype(np.float64), z["vsol"].astype(np.float64)
n = len(S)
spans = json.load(open(f"{D}/spans.json"))
COH = np.array(sorted({int(x) for x in json.load(open(f"{L.D}/cohort.json"))["ids"]}), dtype=np.uint64)
NAM = np.array(sorted(L.NAMED64), dtype=np.uint64)
OUR = np.array(sorted(L.OURS64), dtype=np.uint64)
isC = np.isin(U, COH); isN = np.isin(U, NAM); isO = np.isin(U, OUR)
isF = (isC | isN) & ~isO                      # follower bots
print("loaded", n, flush=True)
fz = np.load(f"{D}/fails.npz")
FS_, FI_, FP_, FM_, FK_ = fz["slot"], fz["idx"], fz["payer"], fz["mint"], fz["kind"]
fF = (np.isin(FP_, COH) | np.isin(FP_, NAM)) & (FK_ == 1)
gfail = np.sort(FS_[fF])                       # global failed follower-bot buy attempts (slot)
# per-bot activity (trades + failed buys) for the 'distinct bots online' gauge: (slot, bot) sorted by slot
_ba_s = np.r_[S[isF], FS_[fF]]; _ba_u = np.r_[U[isF], FP_[fF]]
_o = np.argsort(_ba_s, kind="stable"); BA_S, BA_U = _ba_s[_o], _ba_u[_o]
CORE = np.array(sorted(k for k, v in L.NAMED64.items() if v in L.CORE3), dtype=np.uint64)
coreS = np.sort(np.r_[S[np.isin(U, CORE)], FS_[np.isin(FP_, CORE)]])
print("fails", len(FS_), "bot fails", fF.sum(), flush=True)

gstart = np.r_[0, np.nonzero(M[1:] != M[:-1])[0] + 1]
gend = np.r_[gstart[1:], n]
gid = np.zeros(n, np.int64); gid[gstart[1:]] = 1; gid = np.cumsum(gid)
OFF = np.int64(1) << 34
gkey = gid * OFF + S                          # sorted ascending (mint, slot)

# ---- big dumps chain-wide and whether follower bots / anyone bought within 2 slots after ----
vb = VS + np.where(B == 0, SOL, -SOL)          # vsol before the trade
drop = np.where((B == 0) & (vb > 0), 1 - (VS / np.maximum(vb, 1)) ** 2, 0)
dmp = np.nonzero((B == 0) & (drop >= 0.10) & (SOL >= 0.5e9) & ~isO)[0]
cF = np.r_[0, np.cumsum((isF & (B == 1)).astype(np.int64))]
cBs = np.r_[0, np.cumsum(np.where((B == 1) & ~isO, SOL, 0))]
e2 = np.searchsorted(gkey, gkey[dmp] + 2, side="right")
d_slot = S[dmp]; d_fol = (cF[e2] - cF[dmp + 1]) > 0; d_bsol = (cBs[e2] - cBs[dmp + 1]) / 1e9
o = np.argsort(d_slot, kind="stable"); d_slot, d_fol, d_bsol = d_slot[o], d_fol[o], d_bsol[o]
cdf = np.r_[0, np.cumsum(d_fol)]; cdb = np.r_[0, np.cumsum(d_bsol)]
# 12%+ dumps only (our fill type)
d12 = drop[dmp][o] >= 0.12
cd12 = np.r_[0, np.cumsum(d12)]; cd12f = np.r_[0, np.cumsum(d12 & d_fol)]
gF = np.sort(S[isF & (B == 1)])
gAllB = np.sort(S[(B == 1) & ~isO])
print("dumps", len(dmp), "follow rate", d_fol.mean().round(3), flush=True)


def regime(s):
    out = {}
    for w, nm in ((280, "1m"), (1400, "5m"), (8400, "30m")):
        a = np.searchsorted(d_slot, s - w); b = np.searchsorted(d_slot, s - 2)     # windows closed
        nd = b - a
        out[f"g_nd_{nm}"] = nd
        out[f"g_fol_{nm}"] = (cdf[b] - cdf[a]) / nd if nd else np.nan
        out[f"g_bsol_{nm}"] = (cdb[b] - cdb[a]) / nd if nd else np.nan
        n12 = cd12[b] - cd12[a]
        out[f"g_fol12_{nm}"] = (cd12f[b] - cd12f[a]) / n12 if n12 else np.nan
        out[f"g_botbuys_{nm}"] = np.searchsorted(gF, s) - np.searchsorted(gF, s - w)
        out[f"g_buys_{nm}"] = np.searchsorted(gAllB, s) - np.searchsorted(gAllB, s - w)
        out[f"g_bfail_{nm}"] = np.searchsorted(gfail, s) - np.searchsorted(gfail, s - w)
        a2 = np.searchsorted(BA_S, s - w); b2 = np.searchsorted(BA_S, s)
        out[f"g_botsonline_{nm}"] = len(np.unique(BA_U[a2:b2]))
    k = np.searchsorted(coreS, s)
    out["g_core_last"] = s - int(coreS[k - 1]) if k > 0 else 99999
    out["g_core_5m"] = k - np.searchsorted(coreS, s - 1400)
    return out


# ---- per-user index (whale history) ----
uo = np.argsort(U, kind="stable")
Us = U[uo]


def user_rows(u):
    a = np.searchsorted(Us, np.uint64(u)); b = np.searchsorted(Us, np.uint64(u), side="right")
    return uo[a:b]


def in_span_lo(s):
    for _, lo, hi in spans:
        if lo <= s <= hi: return lo
    return None


# per mint: first slot, first trader (creator if covered)
m_first = S[gstart]; m_cre = U[gstart]


def whale_hist(u, s, mint64):
    """whale's own past on OTHER mints, rows with slot < s: number of trades, mints, big buys (>=6%), hold clock"""
    r = user_rows(u)
    r = r[S[r] < s]
    out = {"wh_n": len(r), "wh_mints": 0, "wh_big": 0, "wh_q10": np.nan, "wh_q50": np.nan, "wh_age": np.nan, "wh_sold_frac": np.nan}
    if not len(r): return out
    out["wh_age"] = s - int(S[r].min())
    mm = M[r]
    out["wh_mints"] = len(np.unique(mm))
    big = r[(B[r] == 1) & (TOK[r] >= 0.06 * SUP) & (mm != mint64)]
    out["wh_big"] = len(big)
    # hold clock: for each other mint where it bought, first buy slot -> first sell slot (if before s)
    holds = []; nb = 0
    for mint in np.unique(mm[(B[r] == 1) & (mm != mint64)])[:400]:
        rr = r[mm == mint]
        bs = S[rr][B[rr] == 1]
        ss_ = S[rr][B[rr] == 0]
        if not len(bs): continue
        nb += 1
        fb = bs.min(); after = ss_[ss_ >= fb]
        if len(after): holds.append(after.min() - fb)
    if nb:
        out["wh_sold_frac"] = len(holds) / nb
        if holds:
            h = np.array(holds); out["wh_q10"] = float((h <= 10).mean()); out["wh_q50"] = float((h <= 50).mean())
    return out


def feats(p):
    m64 = p.get("m64") or L.pk64(p["mint"]); g = np.searchsorted(M, np.uint64(m64))
    if g >= n or M[g] != m64: return None
    e = np.searchsorted(M, np.uint64(m64), side="right")
    ss, ii = S[g:e], I[g:e]
    hit = np.nonzero((ss == p["trig_slot"]) & (ii == p["trig_idx"]))[0]
    if not len(hit): return None
    r = g + int(hit[0]); s = int(S[r])
    f = {"cov": 1}
    lo = in_span_lo(s)
    f["age"] = s - int(S[g]); f["age_cens"] = 1 if (lo is None or S[g] <= lo + 2) else 0
    pr = np.arange(g, r)
    pb, pu, ps, psol, ptok = B[pr], U[pr], S[pr], SOL[pr], TOK[pr]
    f["n_prior"] = len(pr)
    f["buyers"] = len(np.unique(pu[pb == 1])); f["sellers"] = len(np.unique(pu[pb == 0]))
    for w in (20, 100, 500):
        mw = ps >= s - w
        f[f"n_{w}"] = int(mw.sum()); f[f"bsol_{w}"] = psol[mw & (pb == 1)].sum() / 1e9; f[f"ssol_{w}"] = psol[mw & (pb == 0)].sum() / 1e9
        f[f"nbuyer_{w}"] = len(np.unique(pu[mw & (pb == 1)]))
    vpre = VS[r] - SOL[r] if B[r] == 1 else VS[r] + SOL[r]
    f["vsol_pre"] = vpre / 1e9; f["vsol_post"] = VS[r] / 1e9
    f["vsol_max"] = VS[pr].max() / 1e9 if len(pr) else vpre / 1e9
    f["dd_ath"] = 1 - (vpre / 1e9 / f["vsol_max"]) ** 2 if f["vsol_max"] > 0 else 0
    f["trig_pct"] = TOK[r] / SUP * 100; f["trig_sol"] = SOL[r] / 1e9
    sgn = np.where(pb == 1, ptok, -ptok)
    if len(pu):
        uu, inv = np.unique(pu, return_inverse=True); hold = np.bincount(inv, weights=sgn) / SUP * 100
        wh = p.get("whale64")
        hs = np.sort(hold[(uu != np.uint64(wh)) if wh else np.ones(len(uu), bool)])[::-1]
        f["top1"] = hs[0] if len(hs) else 0; f["top5"] = hs[:5].sum() if len(hs) else 0
        f["n_h3"] = int((hs >= 3).sum()); f["n_h1"] = int((hs >= 1).sum())
        fb = np.isin(uu, COH) | np.isin(uu, NAM)
        f["bot_hold_n"] = int((fb & (hold > 0.05)).sum()); f["bot_hold_pct"] = float(hold[fb & (hold > 0)].sum())
        # equal-size holder groups (bundle-like): count of holders within 2% relative of another holder >= 1%
        h1 = np.sort(hold[hold >= 1])
        f["eq_n"] = int(np.sum(np.r_[False, np.abs(np.diff(h1)) / np.maximum(h1[1:], 1e-9) < 0.02])) if len(h1) > 1 else 0
        whp = hold[uu == np.uint64(wh)] if wh else []
        f["wh_prehold"] = float(whp[0]) if len(whp) else 0.0
    else:
        for k in ("top1", "top5", "n_h3", "n_h1", "bot_hold_n", "bot_hold_pct", "eq_n", "wh_prehold"): f[k] = 0
    fbm = isF[pr]
    f["bot_tr_n"] = int(fbm.sum()); f["bot_w_n"] = len(np.unique(pu[fbm]))
    f["bot_last_age"] = s - int(ps[fbm].max()) if fbm.any() else 99999
    f["bot_buy_50"] = int((fbm & (pb == 1) & (ps >= s - 50)).sum())
    # bot warmth: earlier big dumps on this token and whether bots followed them
    dd = pr[(pb == 0) & (drop[pr] >= 0.10) & (psol >= 0.5e9)]
    f["tok_dumps"] = len(dd)
    if len(dd):
        e2_ = np.searchsorted(gkey, gkey[dd] + 2, side="right")
        fol = (cF[np.minimum(e2_, r)] - cF[dd + 1]) > 0
        f["tok_dump_fol"] = float(fol.mean())
    else: f["tok_dump_fol"] = np.nan
    # failed follower-bot buy attempts on this token before the trigger / in the pre-fill window
    fa = np.searchsorted(FM_, np.uint64(m64)); fb_ = np.searchsorted(FM_, np.uint64(m64), side="right")
    fs_, fi_, fbt = FS_[fa:fb_], FI_[fa:fb_], fF[fa:fb_]
    pre = (fs_ < s) | ((fs_ == s) & (fi_ < I[r]))
    f["bfail_pre"] = int((fbt & pre).sum()); f["bfail_pre_w"] = len(np.unique(FP_[fa:fb_][fbt & pre]))
    f["bfail_pre_50"] = int((fbt & pre & (fs_ >= s - 50)).sum())
    f["fail_all_pre"] = int(pre.sum())
    if p.get("buy_slot") is not None:
        f["pf_bfail"] = int((fbt & ~pre & (fs_ <= p["buy_slot"] - 2)).sum())
        f["pf_bfail_w"] = len(np.unique(FP_[fa:fb_][fbt & ~pre & (fs_ <= p["buy_slot"] - 2)]))
        f["pf_bfail_last3"] = int((fbt & ~pre & (fs_ <= p["buy_slot"] - 2) & (fs_ >= p["buy_slot"] - 4)).sum())
        f["pf_fail_all"] = int((~pre & (fs_ <= p["buy_slot"] - 2)).sum())
    # creator
    cre = int(m_cre[gid[g]]) if not f["age_cens"] else 0
    f["cre_is_whale"] = 1 if cre and p.get("whale64") == cre else 0
    f.update(regime(s))
    # whale history
    if p.get("whale64"): f.update(whale_hist(p["whale64"], s, m64))
    # ---- PRE-FILL: rows after the trigger with slot <= fill - 2 ----
    fs = p.get("buy_slot")
    q = np.arange(r + 1, e)
    if fs is not None:
        qq = q[S[q] <= fs - 2]
        qb, qu, qsol = B[qq], U[qq], SOL[qq]
        f["pf_slots"] = fs - s
        f["pf_n"] = len(qq); f["pf_bsol"] = qsol[qb == 1].sum() / 1e9; f["pf_ssol"] = qsol[qb == 0].sum() / 1e9
        f["pf_bot_buys"] = int((isF[qq] & (qb == 1)).sum()); f["pf_bot_sells"] = int((isF[qq] & (qb == 0)).sum())
        f["pf_wh_sold"] = int(((qu == np.uint64(p.get("whale64") or 0)) & (qb == 0)).sum())
        f["pf_vmax"] = (VS[qq].max() / VS[r]) if len(qq) else 1.0
        f["pf_vlast"] = (VS[qq[-1]] / VS[r]) if len(qq) else 1.0
        f["pf_vmin"] = (VS[qq].min() / VS[r]) if len(qq) else 1.0
        f["pf_buyers"] = len(np.unique(qu[qb == 1])); f["pf_sellers"] = len(np.unique(qu[qb == 0]))
        f["pf_bot_w"] = len(np.unique(qu[isF[qq]]))
        f["pf_last_gap"] = (fs - 2 - int(S[qq[-1]])) if len(qq) else fs - 2 - s
        gb = (fs - 2) - 20
        f["g_bfail_20s"] = np.searchsorted(gfail, fs - 1) - np.searchsorted(gfail, gb)
        f["g_botbuys_20s"] = np.searchsorted(gF, fs - 1) - np.searchsorted(gF, gb)
        # ---- POST labels (never features) ----
        fh = [p["dip_row"] - g] if p.get("dip_row") is not None else np.nonzero((S[g:e] == fs) & (I[g:e] == p["buy_idx"]) & isO[g:e])[0]
        if len(fh):
            k = g + int(fh[0])
            after = np.arange(k + 1, e); a2 = after[S[after] <= fs + 2]; a1 = after[S[after] <= fs + 1]
            f["L_bot2"] = int((isF[a2] & (B[a2] == 1)).sum()); f["L_bot1"] = int((isF[a1] & (B[a1] == 1)).sum())
            f["L_bsol2"] = SOL[a2][(B[a2] == 1) & ~isO[a2]].sum() / 1e9
            if p.get("dip_row") is not None:     # PAPER: price ~ vsol^2; exit = last row of slot fs+1, costs 2.5% + 0.0033/0.6
                ex = after[S[after] <= fs + 1]
                v_in = VS[k]; v_out = VS[ex[-1]] if len(ex) else v_in
                f["L_paper"] = (v_out / v_in) ** 2 - 1 - 0.025 - 0.0055
            bef = np.arange(g, k + (1 if p.get("dip_row") is not None else 0))[::-1][:6]
            sl = [x for x in bef if B[x] == 0 and not isO[x]]
            if sl:
                d = sl[0]
                f["L_dump_sol"] = SOL[d] / 1e9; f["L_dump_drop"] = drop[d]
                f["L_dump_whale"] = int(U[d] == np.uint64(p.get("whale64") or 0)); f["L_dump_bot"] = int(isF[d])
                f["L_dump_slotgap"] = fs - int(S[d])
    return f


def _one(p):
    p = dict(p)
    if "whale64" not in p: p["whale64"] = L.pk64(p["whale"]) if p.get("whale") else None
    try: return p["key"], feats(p)
    except Exception as ex: return p["key"], None


if __name__ == "__main__" and os.environ.get("NP"):
    from multiprocessing import Pool
    P = pickle.load(open(sys.argv[1], "rb"))
    out = {}
    with Pool(int(os.environ["NP"])) as pool:
        for k, (key, f) in enumerate(pool.imap_unordered(_one, P, chunksize=64)):
            out[key] = f
            if k % 2000 == 0: print(k, len(P), flush=True)
    pickle.dump(out, open(sys.argv[2], "wb"))
    print("done", sum(1 for v in out.values() if v), "of", len(out), flush=True)
elif __name__ == "__main__":
    P = pickle.load(open(sys.argv[1], "rb"))
    out = {}
    for k, p in enumerate(P):
        p = dict(p); p["whale64"] = L.pk64(p["whale"]) if p.get("whale") else None
        try: out[p["key"]] = feats(p)
        except Exception as ex: print("ERR", p["key"], ex, flush=True); out[p["key"]] = None
        if k % 250 == 0: print(k, len(P), flush=True)
    pickle.dump(out, open(sys.argv[2], "wb"))
    print("done", sum(1 for v in out.values() if v), "of", len(out), flush=True)
