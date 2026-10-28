#!/usr/bin/env python3
"""SELECT step 1 (read-only): the dump ENVELOPE with labels and decision-time features.
Envelope (as briefed): every outside sell (not haqq, not our two wallets) whose post-trade price is >= 3 % below the max price of the
last 10 slots (rows before it in slots [s-10, s], incl. its own pre-trade price), curve SOL after > 30.5, token age <= 30 min,
mayhem excluded. Tape = dv8/tab/trades.npy with our wallets' rows removed (we are simulated), haqq kept.
Labels (MEASURED, code-matched lots from pos/p1.pkl; failed attempts from exec/ext raw txs):
  y247 / y248  : a successful buy by that bot lands after the sell, slot <= s+2;  yatt: 247/248 incl. FAILED buy attempts
  yany         : any haqq code;  hq_k: outside rows between the sell and the first 247/248 buy
Features, all from rows/txs BEFORE the sell (or the create): groups
  MKT  market (the s7/u1 28 + broad b2b set: drop, dd10, size, seller type and balance, chunks, flow, age, curve, bursts ...)
  CRE  creator identity/history (prev creates, their peaks / dumps / haqq follow, creator's own trading history)
  SEL  seller identity/history (prev envelope sells on other mints and how often 247/248 followed them, tape activity, creator links)
  HQS  haqq's own state (open lots per bot globally and on this mint, his history on this mint)
  TIM  time of day, market activity (creates last 10 min, envelope sells last 60 s)
(CTX create-tx strings/shape are joined in s2 from s0.)
Out: sniper-data/haqq_dissect/select/env.npz"""
import json, pickle, time, sys, glob, os, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/select"
H = L.HAQQ
SL_AGE = int(1800 / 0.212) + 1


def sparse_max(x):
    lv = [x]; k = 1
    while 2 * k <= len(x):
        p = lv[-1]; lv.append(np.maximum(p[:-k], p[k:])); k *= 2
    return lv


def rmq(lv, lo, hi):
    """max of x[lo:hi] (hi > lo), vectorised"""
    n = hi - lo; k = np.floor(np.log2(np.maximum(n, 1))).astype(int)
    out = np.empty(len(lo))
    for kk in np.unique(k):
        m = k == kk; t = lv[kk]
        out[m] = np.maximum(t[lo[m]], t[hi[m] - (1 << kk)])
    return out


def main():
    t0 = time.time()
    ids, idm = L.ids_map()
    hq = idm[H]; ours = [idm[w] for w in L.WAL.values() if w in idm]
    CR = json.load(open(f"{L.TAB}/creates.json"))
    # ---- haqq lots (code-matched) and failed attempts
    Z = pickle.load(open("/home/moiz/sniper-data/haqq_dissect/pos/p1.pkl", "rb")); B = Z["buys"]; LO = Z["lots"]
    hl = collections.defaultdict(list)          # mint id -> [(slot, idx, code, cc, close_cc, net)]
    sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos")
    from plib import load
    _, LO2, _ = load()
    lots = []
    for l in LO2:
        b = B[l["b"]]; m = idm.get(l["mint"])
        if m is None or l.get("code") is None: continue
        cc = float(b["cc"]); ccl = l.get("cclose_cc") or (cc + 300000.0)      # never closed: counted open 300 s
        lots.append((m, int(b["slot"]), int(b["idx"]), int(l["code"]), cc, float(ccl), float(l["cnet"]), float(l["cost"])))
    LT = np.array(lots, dtype=[("m", "i8"), ("s", "i8"), ("i", "i8"), ("code", "i4"), ("cc", "f8"), ("ccl", "f8"), ("net", "f8"), ("cost", "f8")])
    LT = LT[np.lexsort((LT["i"], LT["s"], LT["m"]))]
    print(f"haqq lots {len(LT):,} ({time.time() - t0:.0f}s)", flush=True)
    fails = []
    for f in glob.glob("/home/moiz/sniper-data/haqq_dissect/exec/ext/*.jsonl"):
        for line in open(f):
            if H not in line or '"err":null' in line: continue
            try: d = json.loads(line)
            except Exception: continue
            if not d.get("signers") or d["signers"][0] != H or d.get("err") is None: continue
            if not any(x.startswith("Buy") or x.startswith("Trade") for x in (d.get("ixn") or [])): continue
            for mm in d.get("mints") or []:
                m = idm.get(mm)
                if m is not None: fails.append((m, d["s"], d["i"], (d.get("cup") or 0) % 1000))
    FA = np.array(sorted(set(fails)), dtype=np.int64).reshape(-1, 4)
    FAm = collections.defaultdict(list)
    for r in FA.tolist(): FAm[r[0]].append(r)
    FAm = {k: np.array(v, np.int64) for k, v in FAm.items()}
    print(f"haqq failed buy attempts {len(FA):,} (codes {collections.Counter(FA[:, 3].tolist()).most_common(6)}) ({time.time() - t0:.0f}s)", flush=True)
    # ---- tape
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    user = np.asarray(T["user"]).astype(np.int64)
    keep = ~np.isin(user, ours)
    cols = {c: np.asarray(T[c])[keep] for c in ("slot", "idx", "mint", "buy", "sol", "tok", "vsol", "vtok", "bt", "signer")}
    user = user[keep]; del keep
    sl = cols["slot"].astype(np.int64); ix = cols["idx"].astype(np.int64); mi = cols["mint"].astype(np.int64)
    bu = cols["buy"].astype(bool); so = cols["sol"] / 1e9; tk = cols["tok"].astype(np.float64); vs = cols["vsol"] / 1e9
    vt = cols["vtok"].astype(np.float64); bt = cols["bt"].astype(np.int64); sg = cols["signer"].astype(np.int64); del cols
    S0 = int(sl.min())
    ccg = L.cc(sl, ix)
    print(f"tape {len(sl):,} rows ({time.time() - t0:.0f}s)", flush=True)
    # ---- per-user history keys (whole tape, chain order): trades before t, distinct mints before t
    ukey = (user.astype(np.uint64) << np.uint64(41)) | ((sl - S0).astype(np.uint64) << np.uint64(13)) | np.minimum(ix, 8191).astype(np.uint64)
    o = np.argsort(ukey, kind="stable"); UK = ukey[o]
    um_key = user * 10_000_000 + mi
    _, fi = np.unique(um_key, return_index=True)
    UKF = np.sort(ukey[fi])                                            # first touch of (user, mint)
    UKS = np.sort(ukey[~bu])                                           # sells
    del o, um_key, fi
    def ucount(KK, u, s, i):
        q = (u.astype(np.uint64) << np.uint64(41)) | ((s - S0).astype(np.uint64) << np.uint64(13)) | np.minimum(i, 8191).astype(np.uint64)
        q0 = u.astype(np.uint64) << np.uint64(41)
        return (np.searchsorted(KK, q) - np.searchsorted(KK, q0)).astype(np.float32)
    print(f"user keys ({time.time() - t0:.0f}s)", flush=True)
    # ---- creates by creator (all creates in the recording, incl. mayhem)
    crl = []
    for k, c in CR.items():
        if c.get("slot") is None: continue
        crl.append((idm.get(c.get("creator"), -1), int(c["slot"]), int(c.get("idx") or 0), idm.get(k, -1), bool(c.get("mayhem"))))
    CA = np.array(crl, dtype=[("cr", "i8"), ("s", "i8"), ("i", "i8"), ("m", "i8"), ("may", "?")])
    CA = CA[np.lexsort((CA["i"], CA["s"], CA["cr"]))]
    crk = CA["cr"] * 10**10 + (CA["s"] - S0)
    by_cr = collections.defaultdict(list)
    for r in range(len(CA)): by_cr[int(CA["cr"][r])].append(r)
    cs_sorted = np.sort(CA["s"])
    # ---- per-mint spans
    o = np.argsort(mi, kind="stable")
    sl, ix, mi, bu, so, tk, vs, vt, bt, user, sg, ccg = (x[o] for x in (sl, ix, mi, bu, so, tk, vs, vt, bt, user, sg, ccg))
    del o
    um, st = np.unique(mi, return_index=True); en = np.append(st[1:], len(mi))
    span = {int(m): (int(a), int(b)) for m, a, b in zip(um, st, en)}
    print(f"mint spans {len(span):,} ({time.time() - t0:.0f}s)", flush=True)
    # ---- per-mint summary for creator history: (slot array, cummax vsol, creator cum sold/bought tokens) for multi-create creators
    multi = {cr for cr, rs in by_cr.items() if len(rs) >= 2 and cr >= 0}
    msum = {}
    for r in range(len(CA)):
        cr = int(CA["cr"][r]); m = int(CA["m"][r])
        if cr not in multi or m not in span: continue
        a, b = span[m]
        s_ = sl[a:b]; v_ = vs[a:b]; u_ = user[a:b]; b_ = bu[a:b]; k_ = tk[a:b]
        isc = u_ == cr
        msum[m] = (s_, np.maximum.accumulate(v_), np.cumsum(np.where(isc & b_, k_, 0.0)), np.cumsum(np.where(isc & ~b_, k_, 0.0)))
    LTm = {}
    for m in np.unique(LT["m"]).tolist():
        a = np.searchsorted(LT["m"], m); b = np.searchsorted(LT["m"], m, side="right"); LTm[m] = (a, b)
    print(f"creator summaries {len(msum):,} ({time.time() - t0:.0f}s)", flush=True)
    # ---- the per-mint envelope pass
    E = collections.defaultdict(list)
    nm = 0
    LIMIT = int(os.environ.get("LIMIT", "0")); nseen = 0
    for m, (a, e) in span.items():
        nseen += 1
        if LIMIT and nseen > LIMIT: break
        c = CR.get(ids[m])
        if not c or c.get("slot") is None or c.get("mayhem") or e - a < 4: continue
        cs = int(c["slot"]); cr = idm.get(c.get("creator"), -2)
        hi_ = a + int(np.searchsorted(sl[a:e], cs + SL_AGE + 3, side="right"))
        e2 = hi_
        if e2 - a < 4: continue
        s_ = sl[a:e2]; u_ = user[a:e2]; b_ = bu[a:e2]; o_ = so[a:e2]; k_ = tk[a:e2]; v_ = vs[a:e2]; w_ = vt[a:e2]; c_ = ccg[a:e2]
        n = e2 - a
        v_c = float(c.get("vsol") or 30e9) / 1e9; t_c = float(c.get("vtok") or 1.073e15)
        px = v_ / np.maximum(w_, 1); pxp = np.empty(n); pxp[0] = v_c / t_c; pxp[1:] = px[:-1]
        ishq = u_ == hq; outside = ~ishq
        age_sl = s_ - cs
        cand0 = np.flatnonzero(outside & ~b_ & (v_ > 30.5) & (age_sl * 0.212 <= 1800))
        if not len(cand0): continue
        lo10 = np.searchsorted(s_, s_[cand0] - 10)
        lv = sparse_max(px)
        wmax = np.where(cand0 > lo10, rmq(lv, lo10, np.maximum(cand0, lo10 + 1)), 0.0)
        wmax = np.maximum(wmax, pxp[cand0])
        dd10 = 1 - px[cand0] / wmax
        keepc = dd10 >= 0.03
        cand = cand0[keepc]; dd10 = dd10[keepc]
        if not len(cand): continue
        nm += 1
        drop = 1 - px / pxp
        # cumulative helpers
        bsol = np.where(b_ & outside, o_, 0.0); ssol = np.where(~b_ & outside, o_, 0.0)
        cb = np.concatenate([[0], np.cumsum(bsol)]); csl = np.concatenate([[0], np.cumsum(ssol)])
        ntr_c = np.concatenate([[0], np.cumsum(np.ones(n))])
        _, first_idx = np.unique(u_, return_index=True); fs = np.zeros(n, bool); fs[first_idx] = True; cw = np.cumsum(fs)
        bund_mask = (s_ == cs) & b_; early_mask = (s_ <= cs + 10) & b_
        bund = set(u_[bund_mask].tolist()); early = set(u_[early_mask].tolist())
        bundle_sol = float(o_[bund_mask & (u_ != cr)].sum()); n_bund = len(bund - {cr}); n_early = len(early - {cr})
        early_sol = float(o_[early_mask & (u_ != cr)].sum())
        devb = np.cumsum(np.where(b_ & (u_ == cr), o_, 0.0)); devs = np.cumsum(~b_ & (u_ == cr))
        ath = np.maximum.accumulate(px)
        isdump = outside & ~b_ & (drop >= 0.05)
        dk = np.flatnonzero(isdump)
        # seller balance before (tokens), first buy slot, chunk counts: per-user order
        ou = np.lexsort((np.arange(n), u_)); us_ = u_[ou]
        stok = np.where(b_, k_, -k_)[ou]
        grp_start = np.r_[True, us_[1:] != us_[:-1]]
        gid = np.cumsum(grp_start) - 1
        cs_tok = np.cumsum(stok); base = np.where(grp_start, cs_tok - stok, 0); base = np.maximum.accumulate(np.where(grp_start, np.arange(n), 0))
        cum_before = cs_tok - stok - (cs_tok - stok)[base]          # balance before row, within user group
        bal_before = np.empty(n); bal_before[ou] = cum_before
        # first buy slot of each user
        fb_slot = {}
        for r in np.flatnonzero(b_).tolist():
            uu = int(u_[r])
            if uu not in fb_slot: fb_slot[uu] = int(s_[r])
        # sells per user for chunk counts
        sk = np.flatnonzero(~b_)
        skey = u_[sk] * 10**9 + s_[sk]
        oo = np.argsort(skey, kind="stable"); skey_s = skey[oo]
        # haqq lots on this mint
        la, lb = LTm.get(m, (0, 0)); hL = LT[la:lb]
        fa = FAm.get(m, np.zeros((0, 4), np.int64))
        key_ = s_ * 100000 + ix[a:e2]
        for j, d10 in zip(cand.tolist(), dd10.tolist()):
            s = int(s_[j]); i = int(ix[a + j]); sel = int(u_[j]); ccj = float(c_[j])
            lo3 = int(np.searchsorted(s_, s - 3)); lo10_ = int(np.searchsorted(s_, s - 10)); lo30 = int(np.searchsorted(s_, s - 30)); lo47 = int(np.searchsorted(s_, s - 47))
            pdk = dk[dk < j]
            bal = bal_before[j]
            ch10 = int(np.searchsorted(skey_s, sel * 10**9 + s, side="right") - np.searchsorted(skey_s, sel * 10**9 + s - 10))
            ch30 = int(np.searchsorted(skey_s, sel * 10**9 + s, side="right") - np.searchsorted(skey_s, sel * 10**9 + s - 30))
            fbs = fb_slot.get(sel)
            # labels
            after = (hL["s"] > s) | ((hL["s"] == s) & (hL["i"] > i))
            win = after & (hL["s"] <= s + 2)
            y247 = bool((win & (hL["code"] == 247)).any()); y248 = bool((win & (hL["code"] == 248)).any()); yany = bool(win.any())
            ybig = win & np.isin(hL["code"], (247, 248))
            hq_k = -1; hq_net = 0.0
            if ybig.any():
                fl = int(np.flatnonzero(ybig)[0])
                rr = int(np.searchsorted(key_, int(hL["s"][fl]) * 100000 + int(hL["i"][fl])))
                hq_k = int(outside[j + 1:rr].sum())
                hq_net = float(hL["net"][ybig].sum())
            yatt = y247 or y248
            if not yatt and len(fa):
                fw = ((fa[:, 1] > s) | ((fa[:, 1] == s) & (fa[:, 2] > i))) & (fa[:, 1] <= s + 2) & np.isin(fa[:, 3], (247, 248))
                yatt = bool(fw.any())
            # haqq state on this mint
            before = hL["cc"] < ccj
            h_open_tok = int((before & (hL["ccl"] > ccj)).sum()); h_open_tok_big = int((before & (hL["ccl"] > ccj) & np.isin(hL["code"], (247, 248))).sum())
            h_prev_lots = int(before.sum()); h_prev_net = float(hL["net"][hL["ccl"] < ccj].sum())
            b10 = cb[j] - cb[lo47]; s10 = csl[j] - csl[lo47]; b30 = cb[j] - cb[max(int(np.searchsorted(s_, s - 141)), 0)]
            f = dict(
                # MKT
                drop=drop[j], dd10=d10, sell_sol=o_[j], sell_pct=k_[j] / 1e13, vpost=v_[j], age_s=(s - cs) * 0.212, n_tr=j, n_wal=cw[j],
                sel_dev=float(sel == cr), sel_cs=float(sel in bund), sel_early=float(sel in early), sel_bal=bal / 1e13,
                sel_frac=k_[j] / max(bal, k_[j]), sel_arm=(s - fbs) if fbs is not None else -1, ch10=ch10, ch30=ch30,
                devsold=float(devs[j]), devb=float(devb[j]), b3=cb[j] - cb[lo3], s3=csl[j] - csl[lo3], b10s=cb[j] - cb[lo10_], s10s=csl[j] - csl[lo10_],
                b30s=cb[j] - cb[lo30], s30s=csl[j] - csl[lo30], b10=b10, s10=s10, b30r=b10 / max(b30, 1e-3), ntr10=j - lo47,
                ath_dd=1 - px[j] / ath[j], vs_launch=v_[j] / v_c, last_dump_s=((s - s_[pdk[-1]]) * 0.212 if len(pdk) else 999.0), n_dumps=len(pdk),
                bundle_sol=bundle_sol, nd_buy=cb[j] - (devb[j] if True else 0),
                # extra (new, mint structure)
                n_bund=n_bund, n_early=n_early, early_sol=early_sol, sg_diff=float(sg[a + j] != sel),
                # HQS (on this mint)
                h_open_tok=h_open_tok, h_open_tok_big=h_open_tok_big, h_prev_lots=h_prev_lots, h_prev_net=h_prev_net)
            E["m"].append(m); E["s"].append(s); E["i"].append(i); E["cc"].append(ccj); E["bt"].append(int(bt[a + j])); E["sel"].append(sel)
            E["cr"].append(cr); E["cs"].append(cs); E["y247"].append(y247); E["y248"].append(y248); E["yany"].append(yany); E["yatt"].append(yatt)
            E["hq_k"].append(hq_k); E["hq_net"].append(hq_net)
            for k, v in f.items(): E["f_" + k].append(float(v))
        if nm % 5000 == 0: print(f"  mints {nm:,}, events {len(E['m']):,} ({time.time() - t0:.0f}s)", flush=True)
    N = len(E["m"])
    A = {k: np.array(v) for k, v in E.items()}
    print(f"envelope {N:,} events on {nm:,} mints; y247 {A['y247'].sum():,} y248 {A['y248'].sum():,} ({time.time() - t0:.0f}s)", flush=True)
    # ---- SEL: seller identity / history (whole tape, before the sell)
    sel_ = A["sel"].astype(np.int64); s_e = A["s"].astype(np.int64); i_e = A["i"].astype(np.int64)
    A["f_sel_ntr"] = ucount(UK, sel_, s_e, i_e); A["f_sel_nmint"] = ucount(UKF, sel_, s_e, i_e); A["f_sel_nsell"] = ucount(UKS, sel_, s_e, i_e)
    # prev envelope sells by the same seller on OTHER mints, and how many were followed by 247/248 (known: slot <= s-3)
    yb = (A["y247"] | A["y248"]).astype(np.int64)
    o = np.lexsort((i_e, s_e, sel_)); ks = sel_[o] * 10**8 + (s_e[o] - S0); ys = yb[o]; cy = np.concatenate([[0], np.cumsum(ys)])
    q_all = np.searchsorted(ks, sel_ * 10**8 + (s_e - S0)) - np.searchsorted(ks, sel_ * 10**8)
    q3 = np.searchsorted(ks, sel_ * 10**8 + (s_e - S0 - 2)); q0 = np.searchsorted(ks, sel_ * 10**8)
    y_all3 = cy[q3] - cy[q0]
    # same mint part
    mk = A["m"].astype(np.int64)
    _, pid = np.unique(sel_ * 10**6 + mk, return_inverse=True); pid = pid.astype(np.int64)
    o2 = np.lexsort((i_e, s_e, pid)); key2 = pid[o2] * 10**8 + (s_e[o2] - S0); cy2 = np.concatenate([[0], np.cumsum(yb[o2])])
    base2 = pid * 10**8
    q_m = np.searchsorted(key2, base2 + (s_e - S0)) - np.searchsorted(key2, base2)
    y_m3 = cy2[np.searchsorted(key2, base2 + (s_e - S0 - 2))] - cy2[np.searchsorted(key2, base2)]
    A["f_sel_prev_env"] = (q_all - q_m).astype(np.float32); A["f_sel_prev_y"] = (y_all3 - y_m3).astype(np.float32)
    A["f_sel_prev_rate"] = np.where(A["f_sel_prev_env"] > 0, A["f_sel_prev_y"] / np.maximum(A["f_sel_prev_env"], 1), -1)
    # seller is a creator of other tokens (creates before now), seller was a creation-slot buyer... (cs-buyer of THIS mint is MKT)
    crk_s = np.sort(crk)
    A["f_sel_ncreates"] = (np.searchsorted(crk_s, sel_ * 10**10 + (s_e - S0)) - np.searchsorted(crk_s, sel_ * 10**10)).astype(np.float32)
    print(f"SEL done ({time.time() - t0:.0f}s)", flush=True)
    # ---- CRE: creator history, per mint at its create
    crv = A["cr"].astype(np.int64); csv = A["cs"].astype(np.int64)
    um_e, inv = np.unique(mk, return_inverse=True)
    cre = np.full((len(um_e), 11), np.nan, np.float32)
    first_of = np.zeros(len(um_e), np.int64); first_of[inv[::-1]] = np.arange(len(mk))[::-1]
    for q, m in enumerate(um_e.tolist()):
        k = first_of[q]; cr = int(crv[k]); cs = int(csv[k])
        rs = by_cr.get(cr, [])
        prev = [r for r in rs if (CA["s"][r], CA["m"][r]) != (cs, m) and CA["s"][r] < cs]
        last = prev[-50:]
        n_prev = len(prev); n24 = sum(1 for r in prev if CA["s"][r] >= cs - int(86400 / 0.212))
        peaks = []; dumped = 0; hqf = 0; hqbig = 0; hqnet = 0.0; nmay = 0
        T_cc = float(L.cc(np.array([cs]), np.array([0]))[0])
        for r in last:
            pm = int(CA["m"][r]); nmay += bool(CA["may"][r])
            ms_ = msum.get(pm)
            if ms_ is not None:
                p = int(np.searchsorted(ms_[0], cs)) - 1
                if p >= 0:
                    if not CA["may"][r]: peaks.append(float(ms_[1][p]))
                    if ms_[2][p] > 0 and ms_[3][p] >= 0.5 * ms_[2][p]: dumped += 1
            la, lb = LTm.get(pm, (0, 0))
            if lb > la:
                hl_ = LT[la:lb]; bb = hl_["cc"] < T_cc
                hqf += bool(bb.any()); hqbig += bool((bb & np.isin(hl_["code"], (247, 248))).any())
                hqnet += float(hl_["net"][hl_["ccl"] < T_cc].sum())
        last_gap = ((cs - CA["s"][prev[-1]]) * 0.212) if prev else 1e6
        cre[q] = (n_prev, n24, max(peaks) if peaks else -1, np.mean(peaks) if peaks else -1, (np.mean(np.array(peaks) > 50) if peaks else -1),
                  dumped / max(len(last), 1) if last else -1, hqf, hqbig, hqnet, min(last_gap, 1e6), nmay)
    names = ["cr_prev", "cr_prev24", "cr_peak_max", "cr_peak_mean", "cr_peak50", "cr_dumped", "cr_hq", "cr_hqbig", "cr_hqnet", "cr_gap_s", "cr_nmay"]
    for k, nmn in enumerate(names): A["f_" + nmn] = cre[inv, k]
    # creator's own trading history before the create (whole tape)
    csi = np.zeros(len(mk), np.int64)
    cr_ok = crv >= 0
    A["f_cr_ntr"] = np.where(cr_ok, ucount(UK, np.maximum(crv, 0), csv, csi), -1).astype(np.float32)
    A["f_cr_nmint"] = np.where(cr_ok, ucount(UKF, np.maximum(crv, 0), csv, csi), -1).astype(np.float32)
    print(f"CRE done ({time.time() - t0:.0f}s)", flush=True)
    # ---- HQS global: open lots per bot at the sell, seconds since that bot's last buy anywhere
    cce = A["cc"].astype(np.float64)
    for code in (247, 248, 244, 226):
        Lc = LT[LT["code"] == code]
        bcc = np.sort(Lc["cc"]); ccl = np.sort(Lc["ccl"])
        A[f"f_h_open{code}"] = (np.searchsorted(bcc, cce) - np.searchsorted(ccl, cce)).astype(np.float32)
        p = np.searchsorted(bcc, cce) - 1
        A[f"f_h_since{code}"] = np.where(p >= 0, (cce - bcc[np.maximum(p, 0)]) / 1000, 1e5).astype(np.float32)
        A[f"f_h_n60_{code}"] = (np.searchsorted(bcc, cce) - np.searchsorted(bcc, cce - 60000)).astype(np.float32)
    allc = np.sort(LT["cc"]); allcl = np.sort(LT["ccl"])
    A["f_h_open_all"] = (np.searchsorted(allc, cce) - np.searchsorted(allcl, cce)).astype(np.float32)
    # ---- TIM
    A["f_t_hour"] = np.array([(b + 18000) % 86400 / 3600 for b in A["bt"]], np.float32)
    A["f_t_creates10m"] = (np.searchsorted(cs_sorted, s_e) - np.searchsorted(cs_sorted, s_e - int(600 / 0.212))).astype(np.float32)
    es = np.sort(cce)
    A["f_t_env60"] = (np.searchsorted(es, cce) - np.searchsorted(es, cce - 60000)).astype(np.float32)
    A["day"] = ((A["bt"] - L.DAY0) // 86400).astype(np.int8)
    np.savez(f"{OUT}/env{'_test' if LIMIT else ''}.npz", **A)
    print(f"saved {N:,} events, {sum(k.startswith('f_') for k in A)} features ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
