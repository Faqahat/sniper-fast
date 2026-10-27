#!/usr/bin/env python3
"""HAQQ_STRAT step 7 (read-only, offline): the dump universe on the whole tape (10-23 19:26 -> 10-27 23:20 PKT) with causal
features, the haqq label, and OUR simulated outcome per landing scenario and exit rule.
Candidate = an outside sell (not haqq, not ours) with a single-trade price drop >= 5%, sell >= 0.5 SOL, curve SOL after the sell
> 30.52 (not a dead curve), token age <= 30 min.
Label  hq = haqq landed a BUY (tape) on the mint after the dump and within 2 slots, before the next >= 5% outside dump.
Entry  = first tape row whose chain clock is later than the dump + L ms. L: 'ideal' (right after the dump), fixed 30/50/75/100 ms,
         'real' = a draw from OUR measured landed regular buys in the window (h2h.pkl u_ms; seeded per candidate).
         Price check = entry price / post-dump price (guard: 1.05 today).
Exit   = timer H slots after the entry slot (state after the last trade of slot entry+H), or TP/SL with a cap (trigger seen on a trade,
         sold at the state at the end of the next slot). Our buy is put into the curve (constant product); later trades keep their SOL.
         'f20' = the same with 20% of the outside buy SOL between entry and exit removed (fewer followers).
P&L gross of tx costs, at SIZE SOL, pump fee 1.25% each side.
Out: /home/moiz/sniper-data/haqq_strat/uni.npz"""
import json, time, pickle, sys
import numpy as np
TAB = "/home/moiz/sniper-data/haqq_model/tab"; D = "/home/moiz/sniper-data/haqq_strat"
HAQQ = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
OURS = ("2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR")
FB = set(json.load(open("/home/moiz/sniper/ops/strategies/presend/filter/fbots_frozen.json")))
SIZE = 0.4; FEE = 0.0125; SMS = 212.0
LS = ("ideal", "l30", "l50", "l75", "l100", "real")
HS = (2, 3, 5, 8, 12, 20, 30)
TPSL = ((0.10, 0.10, 8), (0.10, 0.20, 12), (0.15, 0.15, 20), (0.20, 0.30, 30), (0.08, 1.0, 5))
FEATS = ["drop", "sell_sol", "sell_pct", "vpost", "age_s", "n_tr", "n_wal", "nd_buy", "dev_sold", "d_dev", "d_bund", "d_early", "d_fb",
         "b10", "s10", "nb3", "ath_dd", "vs_launch", "last_dump_s", "n_dumps", "hq_prev", "hq_open", "fb_n", "bundle_sol", "dev_buy",
         "b30_ratio", "trades_10s", "hour"]


def main():
    t0 = time.time()
    ids = json.load(open(f"{TAB}/ids.json")); idm = {k: i for i, k in enumerate(ids)}
    h = idm[HAQQ]; our = [idm[w] for w in OURS if w in idm]
    fb_ids = np.array(sorted(idm[w] for w in FB if w in idm), np.int64)
    T = np.load(f"{TAB}/trades.npy")
    S = np.load(f"{TAB}/slots.npy"); s0 = int(S["slot"].min())
    bsz = np.zeros(int(S["slot"].max()) - s0 + 1, np.float64); bsz[S["slot"].astype(np.int64) - s0] = S["maxi"].astype(np.int64) + 1
    bsz[bsz <= 0] = 400
    o = np.argsort(T["mint"], kind="stable"); T = T[o]
    um, st_ = np.unique(T["mint"], return_index=True); en_ = np.append(st_[1:], len(T))
    CR = json.load(open(f"{TAB}/creates.json"))
    h2h = pickle.load(open(f"{D}/h2h.pkl", "rb"))
    real_ms = np.array([e["u_ms"] for e in h2h if e["kind"] == "regular" and e["us"] and e["u_ms"] is not None], float)
    print(f"tape {len(T):,}; real landing sample {len(real_ms)} p50 {np.median(real_ms):.0f} ms ({time.time() - t0:.0f}s)", flush=True)
    rng = np.random.default_rng(7)
    X = []; META = []; OUTC = []
    for mi, a, e in zip(um.tolist(), st_.tolist(), en_.tolist()):
        c = CR.get(ids[mi])
        if not c or c.get("slot") is None or e - a < 8: continue
        cs = int(c["slot"]); cr = idm.get(c.get("creator"), -2)
        sl = T["slot"][a:e].astype(np.int64); ix = T["idx"][a:e].astype(np.int64); us = T["user"][a:e].astype(np.int64)
        bu = T["buy"][a:e].astype(bool); so = T["sol"][a:e] / 1e9; tk = T["tok"][a:e].astype(np.float64)
        vs = T["vsol"][a:e] / 1e9; vt = T["vtok"][a:e].astype(np.float64); bt = T["bt"][a:e].astype(np.int64)
        n = len(sl)
        px = vs / np.maximum(vt, 1)
        v_c = float(c.get("vsol") or 30e9) / 1e9; t_c = float(c.get("vtok") or 1.073e15)
        pxp = np.empty(n); pxp[0] = v_c / t_c; pxp[1:] = px[:-1]
        drop = np.where(~bu, 1 - px / pxp, 0.0)
        ishq = us == h; isour = np.isin(us, our); outside = ~ishq & ~isour
        cand = np.flatnonzero(outside & ~bu & (drop >= 0.05) & (so >= 0.5) & (vs > 30.52) & ((sl - cs) * 0.212 <= 1800))
        if not len(cand): continue
        cc = sl * SMS + ix / np.maximum(bsz[np.clip(sl - s0, 0, len(bsz) - 1)], ix + 1.0) * SMS
        bsol = np.where(bu & outside, so, 0.0); ssol = np.where(~bu & outside, so, 0.0)
        cb = np.cumsum(bsol); cs_ = np.cumsum(ssol)
        nd = np.where(bu & outside & (us != cr), so, 0.0); cnd = np.cumsum(nd)
        devs = np.cumsum(~bu & (us == cr)); devb = np.cumsum(np.where(bu & (us == cr), so, 0.0))
        firstseen = np.zeros(n, bool); seen = set()
        for k in range(n):
            u = int(us[k])
            if u not in seen: seen.add(u); firstseen[k] = True
        cw = np.cumsum(firstseen)
        isfb = np.isin(us, fb_ids); cfb = np.cumsum(firstseen & isfb)
        ath = np.maximum.accumulate(px)
        bund = set(us[(sl == cs) & bu].tolist()); early = set(us[(sl <= cs + 10) & bu].tolist())
        bundle_sol = float(so[(sl == cs) & bu & (us != cr)].sum())
        chq = np.cumsum(ishq); hq_bal = np.cumsum(np.where(ishq, np.where(bu, tk, -tk), 0.0))
        dumpk = np.flatnonzero(outside & ~bu & (drop >= 0.05))
        for j in cand.tolist():
            # ---- features (rows <= j)
            lo10 = int(np.searchsorted(sl, sl[j] - 47)); lo3 = int(np.searchsorted(sl, sl[j] - 3)); lo30 = int(np.searchsorted(sl, sl[j] - 141))
            pdk = dumpk[dumpk < j]
            seller = int(us[j])
            b10 = cb[j] - (cb[lo10 - 1] if lo10 > 0 else 0); s10 = cs_[j] - (cs_[lo10 - 1] if lo10 > 0 else 0)
            b30 = cb[j] - (cb[lo30 - 1] if lo30 > 0 else 0)
            f = [drop[j], so[j], tk[j] / 1e13, vs[j], (sl[j] - cs) * 0.212, j, cw[j], cnd[j], float(devs[j] > 0), float(seller == cr),
                 float(seller in bund), float(seller in early), float(isfb[j]), b10, s10, float((bu[lo3:j] & outside[lo3:j]).sum()),
                 1 - px[j] / ath[j], vs[j] / v_c, ((sl[j] - sl[pdk[-1]]) * 0.212 if len(pdk) else 999.0), float(len(pdk)),
                 float(chq[j]), float(hq_bal[j] > 1e6), float(cfb[j]), bundle_sol, float(devb[j]), b10 / max(b30, 1e-3),
                 float(j - lo10), float(time.gmtime(int(bt[j]) + 18000).tm_hour)]
            # ---- label: haqq buy within 2 slots, before the next >= 5% outside dump
            nxt = dumpk[dumpk > j]; lim = int(nxt[0]) if len(nxt) else n
            hi2 = min(int(np.searchsorted(sl, sl[j] + 2, side="right")), lim)
            hq = bool((ishq[j + 1:hi2] & bu[j + 1:hi2]).any())
            hq_fast = bool((ishq[j + 1:min(int(np.searchsorted(sl, sl[j], side="right")), lim)] & bu[j + 1:min(int(np.searchsorted(sl, sl[j], side="right")), lim)]).any())
            # ---- outcomes
            rl = float(real_ms[rng.integers(0, len(real_ms))])
            row_out = []
            for lname, L in zip(LS, (0.0, 30.0, 50.0, 75.0, 100.0, rl)):
                r = int(np.searchsorted(cc, cc[j] + L, side="right")) if L > 0 else j + 1
                r = max(r, j + 1)
                if r >= n:
                    row_out.append([np.nan] * (2 + 2 * len(HS) + len(TPSL))); continue
                v0 = vs[r - 1]; t0_ = vt[r - 1]; K = v0 * t0_
                pr = (v0 / t0_) / px[j]
                Sn = SIZE / (1 + FEE); v1 = v0 + Sn; tok = t0_ - K / v1
                es = max(int(sl[j]), int((cc[j] + L) // SMS))
                vals = [pr, cc[r] - cc[j]]
                for H in HS:
                    q = int(np.searchsorted(sl, es + H, side="right")) - 1
                    if q < r - 1 or sl[-1] < es + H: vals += [np.nan, np.nan]; continue
                    dv = vs[q] - v0; bsum = cb[q] - cb[r - 1]
                    for dd in (dv, dv - 0.2 * bsum):
                        V = v1 + dd; Tn = K / V; pro = (V - K / (Tn + tok)) * (1 - FEE)
                        vals.append(pro - SIZE)
                # TP/SL (trigger on a trade, sell at the end of the next slot)
                capmax = max(x[2] for x in TPSL)
                qmax = int(np.searchsorted(sl, es + capmax + 1, side="right"))
                ww = np.arange(r, qmax)
                if len(ww):
                    V = v1 + (vs[ww] - v0); ret = (V - K / (K / V + tok)) * (1 - FEE) / SIZE - 1
                for tp, slp, cap in TPSL:
                    if sl[-1] < es + cap: vals.append(np.nan); continue
                    if len(ww):
                        okk = (sl[ww] <= es + cap) & ((ret >= tp) | (ret <= -slp))
                        hit = np.flatnonzero(okk)
                    else: hit = []
                    ex_slot = (int(sl[ww[hit[0]]]) + 1) if len(hit) else es + cap
                    q = int(np.searchsorted(sl, ex_slot, side="right")) - 1
                    Vq = v1 + (vs[q] - v0); pro = (Vq - K / (K / Vq + tok)) * (1 - FEE)
                    vals.append(pro - SIZE)
                row_out.append(vals)
            X.append(f); META.append((mi, j + a, int(sl[j]), int(ix[j]), int(bt[j]), hq, hq_fast, cc[j], int(sl[j] - cs)))
            OUTC.append(row_out)
        if len(META) and len(META) % 50000 < len(cand):
            print(f"  {len(META):,} candidates ({time.time() - t0:.0f}s)", flush=True)
    X = np.array(X, np.float32); O = np.array(OUTC, np.float32)
    M = np.array(META, dtype=[("mint", "u4"), ("row", "u8"), ("slot", "u8"), ("idx", "u4"), ("bt", "u4"), ("hq", "?"), ("hq_fast", "?"), ("cc", "f8"), ("age", "i8")])
    np.savez(f"{D}/uni.npz", X=X, O=O, M=M, feats=np.array(FEATS), LS=np.array(LS), HS=np.array(HS), TPSL=np.array(TPSL))
    print(f"done: {len(M):,} candidates, haqq-labelled {M['hq'].mean() * 100:.1f}% ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
