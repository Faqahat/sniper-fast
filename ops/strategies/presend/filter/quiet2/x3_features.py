#!/usr/bin/env python3
"""QUIET2 step 3: chain features at ARM time for every live window and every quiet skip (only chain rows strictly before the
trigger tx + the trigger; whale dumps closed before the trigger slot), chain LABELS for the fills (other wallets' trades between our
buy and our sell), fill-time features, and after-trigger PROXIES for unfilled / skipped windows (never used in a rule).
Output features.json (windows + quiet skips). Read-only."""
import sys, json, collections, bisect, time
import numpy as np
sys.path.insert(0, "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/quiet2")
import q2lib as Q

D = Q.D
COHORT = "/home/moiz/sniper/ops/overnight/sel/cohort_train.json"
FBOTS = "/home/moiz/sniper/ops/strategies/presend/filter/fbots_frozen.json"
SUPPLY = 10 ** 15
t0 = time.time()
C = np.load(f"{D}/chain.npz"); I = json.load(open(f"{D}/ids.json"))
S, IX, J, BT, BUY, SOL, TOK, VS, VT, MI, UI = (C[k] for k in ("s", "i", "j", "bt", "buy", "sol", "tok", "vsol", "vtok", "mint", "user"))
S = S.astype(np.int64); n = len(S)
mid = {m: k for k, m in enumerate(I["mint"])}; uid = {u: k for k, u in enumerate(I["user"])}
coh = {uid[u] for u in json.load(open(COHORT)) if u in uid}; fb = {uid[u] for u in json.load(open(FBOTS)) if u in uid}
ours = {uid[u] for u in Q.OURS if u in uid}
morder = np.argsort(MI, kind="stable"); msorted = MI[morder]
mstart = np.searchsorted(msorted, np.arange(len(I["mint"]) + 1))
SPAN_LO = I["lo"]
print(f"chain {n} rows, {len(I['mint'])} mints, loaded {time.time()-t0:.0f}s", flush=True)

# ---- whale dump book from the chain (the engine's rule): seller -> sorted list of (slot, bt, nf, mint)
m = (BUY == 0) & (SOL >= 300_000_000) & (VS < 100_000_000_000) & (VT > TOK)
idx = np.nonzero(m)[0]
post = VS[idx].astype(float) / np.maximum(VT[idx].astype(float), 1); pre = (VS[idx] + SOL[idx]).astype(float) / np.maximum((VT[idx] - TOK[idx]).astype(float), 1)
idx = idx[~(post > 0.92 * pre)]
inv = np.empty(n, np.int64); inv[morder] = np.arange(n)
book = collections.defaultdict(list)
for r in idx.tolist():
    mk = int(MI[r]); e = mstart[mk + 1]; p = int(inv[r]); s = int(S[r]); u = int(UI[r]); bs = set(); q = p + 1
    while q < e:
        rr = morder[q]
        if S[rr] > s + 2: break
        if BUY[rr] and UI[rr] != u: bs.add(int(UI[rr]))
        q += 1
    book[u].append((s, int(BT[r]), len(bs), mk))
for v in book.values(): v.sort()
print(f"dumps {len(idx)} sellers {len(book)} {time.time()-t0:.0f}s", flush=True)


def mint_rows(mk):
    return morder[mstart[mk]:mstart[mk + 1]]


def find_trig(rows, slot, tidx, wh):
    k = np.nonzero((S[rows] == slot) & (IX[rows] == tidx) & (BUY[rows] == 1))[0]
    if len(k) == 0: return None
    if len(k) > 1:
        kk = [x for x in k if UI[rows[x]] == wh]
        k = kk if kk else list(k)
    return int(k[0])


def arm_feats(r):
    f = {}
    mk = mid.get(r["mint"]); wh = uid.get(r["whale"], -1)
    if mk is None: f["chain_ok"] = False; return f
    rows = mint_rows(mk); kt = find_trig(rows, r["trig_slot"], r["trig_idx"], wh)
    if kt is None: f["chain_ok"] = False; return f
    f["chain_ok"] = True
    s0 = r["trig_slot"]; bt0 = int(BT[rows[kt]]); R0 = rows[:kt]; tr = rows[kt]
    sl = S[R0]; bt = BT[R0].astype(np.int64); U = UI[R0]; B = BUY[R0]; So = SOL[R0].astype(np.int64); Tk = TOK[R0].astype(np.int64)
    f["n_tr"] = int(len(R0)); f["hist_from_span_start"] = bool(len(R0) and int(bt[0]) - SPAN_LO < 120)   # token older than my chain span?
    f["first_bt"] = int(bt[0]) if len(R0) else bt0
    f["token_age_s"] = bt0 - f["first_bt"]
    for L in (10, 30, 60, 120, 300):
        mm = bt >= bt0 - L
        f[f"n_tr_{L}s"] = int(mm.sum()); f[f"n_buyers_{L}s"] = int(len(set(U[mm & (B == 1)].tolist())))
        f[f"buy_sol_{L}s"] = float(So[mm & (B == 1)].sum()) / 1e9; f[f"sell_sol_{L}s"] = float(So[mm & (B == 0)].sum()) / 1e9
        us = set(U[mm].tolist()); f[f"coh_{L}s"] = len(us & coh); f[f"fb_{L}s"] = len(us & fb)
    f["trades_per_s_60"] = f["n_tr_60s"] / 60.0
    f["since_last_chain"] = int(s0 - sl[-1]) if len(sl) else 9999
    f["since_last_s"] = int(bt0 - bt[-1]) if len(bt) else 9999
    bal = collections.defaultdict(int)
    for u, b, t in zip(U.tolist(), B.tolist(), Tk.tolist()): bal[u] += t if b else -t
    seen = set(U.tolist())
    f["coh_hold_chain"] = sum(1 for u in seen if u in coh and bal[u] > 0); f["fb_n_chain"] = sum(1 for u in seen if u in fb)
    f["coh_ever"] = len(seen & coh); f["n_wallets"] = len(seen)
    hb = [v for v in bal.values() if v > 0]
    f["holders_gt1pct"] = sum(1 for v in hb if v > SUPPLY // 100); f["holders_gt0_5pct"] = sum(1 for v in hb if v > SUPPLY // 200)
    f["top_holder_pct"] = (max(hb) / SUPPLY * 100) if hb else 0.0
    f["n_holders"] = len(hb)
    # the whale on this token
    wb = bal.get(wh, 0); f["whale_bal_pct_before"] = wb / SUPPLY * 100; f["whale_pct_after_buy"] = (wb + int(TOK[tr])) / SUPPLY * 100
    wrows = np.nonzero(U == wh)[0]
    f["whale_prev_trades"] = int(len(wrows)); f["whale_hold_slots"] = int(s0 - sl[wrows[0]]) if len(wrows) else -1
    f["whale_prev_sells_here"] = int(((U == wh) & (B == 0)).sum())
    # price trend: pre-trigger price vs the post price of the last trade >= 30 / 60 / 120 s before; max price in the last 120 s
    pre_p = (int(VS[tr]) - int(SOL[tr])) / max(int(VT[tr]) + int(TOK[tr]), 1); post_p = int(VS[tr]) / max(int(VT[tr]), 1)
    f["pump_pct"] = (post_p / pre_p - 1) * 100; f["lim"] = post_p * 0.88
    pr = VS[R0].astype(float) / np.maximum(VT[R0].astype(float), 1)
    for L in (30, 60, 120):
        k = np.searchsorted(bt, bt0 - L)
        f[f"ret_{L}s"] = (pre_p / pr[k - 1] - 1) * 100 if k >= 1 else 0.0
        f[f"maxdd_{L}s"] = (pre_p / pr[k:].max() - 1) * 100 if k < len(pr) else 0.0
    f["buy_vs_curve"] = int(SOL[tr]) / max(int(VS[tr]), 1)
    f["vsol_pre"] = (int(VS[tr]) - int(SOL[tr])) / 1e9
    # same-slot earlier trades (QUIET (a) is since_last >= 1 <=> none in the trigger slot before it)
    f["same_slot_before"] = int((sl == s0).sum())
    # whale dump history from the chain (closed before the trigger slot: s + 2 < s0), last 24 h and all of my span
    hist = [d for d in book.get(wh, []) if d[0] + 2 < s0 and d[1] >= bt0 - 86400]
    f["wd_n"] = len(hist); f["wd_mean"] = float(np.mean([d[2] for d in hist])) if hist else -1.0
    f["wd_last"] = hist[-1][2] if hist else -1; f["wd_max"] = max((d[2] for d in hist), default=-1)
    f["wd_zero_share"] = (sum(1 for d in hist if d[2] == 0) / len(hist)) if hist else -1.0
    f["wd_n_1h"] = sum(1 for d in hist if d[1] >= bt0 - 3600); f["wd_n_this_mint"] = sum(1 for d in hist if d[3] == mk)
    f["wd_hist_avail_h"] = (bt0 - SPAN_LO) / 3600.0
    f["wd_last_age_s"] = (bt0 - hist[-1][1]) if hist else -1
    # ---- after-trigger (proxies and fill-time; NOT arm-time)
    RA = rows[kt + 1:]
    sa = S[RA]; ua = UI[RA]; ba = BUY[RA]; soa = SOL[RA].astype(np.int64)
    oth = (ua != wh) & ~np.isin(ua, list(ours))
    for L in (0, 1, 2, 3, 4, 5, 6, 7, 8, 10):
        mm = (sa <= s0 + L) & oth
        f[f"after_tr_{L}"] = int(mm.sum()); f[f"after_buyers_{L}"] = int(len(set(ua[mm & (ba == 1)].tolist())))
        f[f"after_buy_sol_{L}"] = float(soa[mm & (ba == 1)].sum()) / 1e9
    pa = VS[RA].astype(float) / np.maximum(VT[RA].astype(float), 1)
    for L in (3, 5, 8):
        mm = sa <= s0 + L
        f[f"px_ret_{L}"] = (pa[mm][-1] / post_p - 1) * 100 if mm.any() else 0.0
    # proxy: the whale's first sell inside the window (<= s0 + 10) whose post price is <= the limit (the try fills): followers =
    # distinct other buyers after it in its slot and the next 2 slots (the DumpBook rule); return = last price within 2 slots vs its post
    f["wsell_n10"] = int(((ua == wh) & (ba == 0) & (sa <= s0 + 10)).sum())
    # proxy fill = the FIRST trade inside the window (<= s0 + 10) whose post price is <= the limit (any seller: our pre-sent try lands on
    # any drop); followers = distinct buyers (not that seller, not us) after it in its slot and the next 2 slots; ret2 = last price
    # within 2 slots vs its post price
    f["px_fill"] = False
    pp_all = pa; inwin = sa <= s0 + 10
    # the engine re-signs each slot's tries at the price it sees then: limit = 0.88 x the last post price of the previous slots
    psign = np.empty(len(RA)); last_p = post_p; last_s = s0; cur_lim_p = post_p
    for k in range(len(RA)):
        if sa[k] > last_s: cur_lim_p = last_p; last_s = sa[k]
        psign[k] = cur_lim_p; last_p = pa[k]
    cand = np.nonzero(inwin & (ba == 0) & (pp_all <= 0.88 * psign))[0]
    if len(cand):
        k = int(cand[0]); rr = RA[k]; pp = pp_all[k]; seller = int(ua[k])
        f["px_fill"] = True; f["px_dump_slot"] = int(S[rr]) - s0; f["px_dump_sol"] = int(SOL[rr]) / 1e9; f["px_dump_post_vsol"] = int(VS[rr]) / 1e9
        f["px_dump_by_whale"] = bool(seller == wh); f["px_dump_is_sell"] = bool(ba[k] == 0)
        f["px_dump_drop"] = (1 - pp / ((int(VS[rr]) + int(SOL[rr])) / max(int(VT[rr]) - int(TOK[rr]), 1))) * 100 if ba[k] == 0 else 0.0
        o2 = (ua != seller) & ~np.isin(ua, list(ours))
        mm = (np.arange(len(RA)) > k) & (sa <= S[rr] + 2) & o2
        f["px_fol_buyers"] = int(len(set(ua[mm & (ba == 1)].tolist()))); f["px_fol_trades"] = int(mm.sum())
        f["px_fol_buy_sol"] = float(soa[mm & (ba == 1)].sum()) / 1e9
        m2 = (np.arange(len(RA)) > k) & (sa <= S[rr] + 2)
        f["px_ret2"] = (pa[m2][-1] / pp - 1) * 100 if m2.any() else 0.0
        m3 = (np.arange(len(RA)) < k) & oth
        f["px_hold_others"] = int(m3.sum()); f["px_hold_buyers"] = int(len(set(ua[m3 & (ba == 1)].tolist())))
        f["px_runup"] = (((int(VS[rr]) + int(SOL[rr])) / max(int(VT[rr]) - int(TOK[rr]), 1)) / post_p - 1) * 100
    f["kt"] = kt
    return f


def fill_feats(r, f):
    """chain labels of a fill: other wallets' trades strictly between our buy and our sell; others between the trigger and our buy"""
    mk = mid[r["mint"]]; rows = mint_rows(mk); wh = uid.get(r["whale"], -1)
    pos = list(zip(S[rows].tolist(), IX[rows].tolist()))
    fpos = (r["fill_slot"], r["fill_idx"]); spos = (r.get("sell_slot") or 10 ** 12, r.get("sell_idx") or 0)
    a = bisect.bisect_right(pos, fpos); b = bisect.bisect_left(pos, spos)
    mid_rows = rows[a:b]; u = UI[mid_rows]; oth = ~np.isin(u, list(ours))
    f["fol_trades"] = int(oth.sum()); f["fol_buys"] = int((oth & (BUY[mid_rows] == 1)).sum())
    f["fol_buyers"] = int(len(set(u[oth & (BUY[mid_rows] == 1)].tolist()))); f["fol_buy_sol"] = float(SOL[mid_rows][oth & (BUY[mid_rows] == 1)].sum()) / 1e9
    f["fol_sell_sol"] = float(SOL[mid_rows][oth & (BUY[mid_rows] == 0)].sum()) / 1e9
    f["fol_whale_sells"] = int(((u == wh) & (BUY[mid_rows] == 0)).sum())
    f["fol_coh_buyers"] = len(set(u[oth & (BUY[mid_rows] == 1)].tolist()) & coh); f["fol_fb_buyers"] = len(set(u[oth & (BUY[mid_rows] == 1)].tolist()) & fb)
    f["our_buy_on_chain"] = bool(a > 0 and pos[a - 1] == fpos)
    tpos = (r["trig_slot"], r["trig_idx"]); c = bisect.bisect_right(pos, tpos)
    pre_rows = rows[c:a - 1] if f["our_buy_on_chain"] else rows[c:a]
    u2 = UI[pre_rows]; oth2 = (u2 != wh) & ~np.isin(u2, list(ours))
    f["others_trig_to_fill"] = int(oth2.sum()); f["others_buys_trig_to_fill"] = int((oth2 & (BUY[pre_rows] == 1)).sum())
    f["buyers_trig_to_fill"] = int(len(set(u2[oth2 & (BUY[pre_rows] == 1)].tolist())))
    f["whale_sells_trig_to_fill"] = int(((u2 == wh) & (BUY[pre_rows] == 0)).sum())
    wsl = np.nonzero(BUY[pre_rows] == 0)[0]
    if len(wsl):
        k = wsl[-1]; rr = pre_rows[k]; pp = int(VS[rr]) / max(int(VT[rr]), 1); seller = int(UI[rr])
        f["dump_by_whale"] = bool(seller == wh)
        f["dump_slot_off"] = int(S[rr]) - r["trig_slot"]; f["dump_sol"] = int(SOL[rr]) / 1e9; f["dump_post_vsol"] = int(VS[rr]) / 1e9
        f["dump_drop"] = (1 - pp / ((int(VS[rr]) + int(SOL[rr])) / max(int(VT[rr]) - int(TOK[rr]), 1))) * 100
        f["dump_vs_curve"] = int(SOL[rr]) / max(int(VS[rr]) + int(SOL[rr]), 1)
        f["dump_tok_pct"] = int(TOK[rr]) / SUPPLY * 100
        f["whale_sold_all"] = bool(seller == wh and int(TOK[rr]) >= 0.98 * (f["whale_pct_after_buy"] / 100 * SUPPLY))
        before = pre_rows[:k]; ub = UI[before]; ob = (ub != wh) & ~np.isin(ub, list(ours))
        f["hold_others"] = int(ob.sum()); f["hold_buyers"] = int(len(set(ub[ob & (BUY[before] == 1)].tolist()))); f["hold_buy_sol"] = float(SOL[before][ob & (BUY[before] == 1)].sum()) / 1e9
        f["hold_coh_buyers"] = len(set(ub[ob & (BUY[before] == 1)].tolist()) & coh); f["hold_fb_buyers"] = len(set(ub[ob & (BUY[before] == 1)].tolist()) & fb)
        f["hold_sells"] = int((ob & (BUY[before] == 0)).sum()); f["hold_sell_sol"] = float(SOL[before][ob & (BUY[before] == 0)].sum()) / 1e9
        after = pre_rows[k + 1:]; ua2 = UI[after]; oa = (ua2 != seller) & ~np.isin(ua2, list(ours))
        f["dump_to_fill_others"] = int(oa.sum()); f["dump_to_fill_buyers"] = int(len(set(ua2[oa & (BUY[after] == 1)].tolist())))
        f["dump_to_fill_same_slot"] = bool(S[rr] == r["fill_slot"])
        post_trig = int(VS[rows[f["kt"]]]) / max(int(VT[rows[f["kt"]]]), 1)
        f["runup"] = (((int(VS[rr]) + int(SOL[rr])) / max(int(VT[rr]) - int(TOK[rr]), 1)) / post_trig - 1) * 100
        f["dump_vs_lim"] = (pp / f["lim"] - 1) * 100
    return f


Wj = json.load(open(f"{D}/windows.json"))
out_w = []; miss = collections.Counter()
for r in Wj["windows"]:
    f = arm_feats(r)
    if f.get("chain_ok") and r["filled"]:
        fill_feats(r, f)
    if not f.get("chain_ok"): miss[r["run"]] += 1
    r["f"] = f; out_w.append(r)
out_s = []
for r in Wj["skips"]:
    if r["why"] != "quiet": continue
    r["f"] = arm_feats(r); out_s.append(r)
    if not r["f"].get("chain_ok"): miss[r["run"] + "_skip"] += 1
print("chain misses", dict(miss), f"{time.time()-t0:.0f}s")
# agreement of the replayed signals with the engine's
agree = collections.Counter()
for r in out_w:
    f = r["f"]
    if not f.get("chain_ok") or r["since_last"] is None: continue
    agree["n"] += 1
    agree["a_ok"] += int((f["since_last_chain"] >= 1) == (r["since_last"] >= 1))
    agree["b_ok"] += int((f["coh_hold_chain"] == 0) == (r["coh_hold"] == 0))
    agree["c_ok"] += int((f["fb_n_chain"] < 2) == (r["fb_n"] < 2))
    if f["wd_hist_avail_h"] >= 24:
        agree["d_n"] += 1; agree["d_count_ok"] += int(f["wd_n"] == r["wh_dumps"]); agree["d_ok"] += int((f["wd_mean"] < 2.24) == (r["wh_fol"] < 2.24))
print("signal agreement", dict(agree))
json.dump(dict(windows=out_w, skips=out_s), open(f"{D}/features.json", "w"))
print("done", len(out_w), len(out_s), f"{time.time()-t0:.0f}s")
