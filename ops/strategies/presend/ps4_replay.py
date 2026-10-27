#!/usr/bin/env python3
# Step 2: replay PRE-SENT CONDITIONAL BUYS on the tapes (read-only, $0).
# A window = a period during which we keep a conditional buy alive on one token (k attempts per slot; the attempt count is a
# COST, charged in ps5). Limit = reference price x (1 - y). The order fills at the first trade x that puts the price <= limit,
# our buy placed after the trades arriving within D ms of x (queue model), at the real post-trade curve state, IF the price
# there is still <= limit (else that attempt fails and we wait for the next crossing). Reference:
#   fixed    = the trigger's post-trade price ("further drop of y after a dump")
#   trailing = the price known LREF ms before the crossing (catches a sudden drop >= y, the pre-placers' style)
# Queue models D: a = right after x; b = after trades within 5 ms; c = within 10 ms (behind the real pre-placers);
#   r1 / r4 / r20 = K attempts per slot -> our first attempt lands U[0, 212/K) ms after x (deterministic hash draw).
# After the fill: dd1_build.path() mechanics (followers whose slippage our buy breaks are dropped, sells as tokens in, pump
# fee both sides, exits = time limit `cap` slots after the entry slot / TP / SL, sells 75 ms into the slot).
# Families (one window per trigger; ps5 applies one-window-per-token arming, W, filters, engine limits and costs):
#   T1  : every >= 2% sell (curve < 100 SOL, age >= 5 slots): fixed ref = its post-dump price, live ARM ms after it, <= 50 slots
#   T1t : same triggers, trailing ref
#   T2  : big holders (creator / create-slot insider / any wallet >= 3% of supply) that have not sold: live from the trade that
#         made them big (+ARM) until their first sell (+30 ms), <= 250 slots; trailing ref
#   T3  : the real pre-placers' targeting (ps3c: most start sending 0-5 s after the create and fill on the first dumps):
#         one window per token from the create (+ARM), <= 250 slots; trailing ref; launch features for filters
# usage: python3 ps4_replay.py R2 [procs]   -> presend/ps4_<day>.npz
import sys, os, json, bisect, zlib, time
import numpy as np
from multiprocessing import get_context
import ps_common as C

SMS = 212.0; SELL_LAT = 75.0; HMAX = 40; GRADV = 110e9; UNTRADE_V = 100e9; SUP = 1e15
ARM = float(os.environ.get("PS_ARM", "50")); LREF = float(os.environ.get("PS_LREF", "50"))
YS = (0.02, 0.03, 0.05, 0.08, 0.12, 0.16, 0.20, 0.25)          # 0.16-0.25 = extension (R2 optimum sat at 0.12)
DMOD = ("a", "b", "c", "r1", "r4", "r20"); DFIX = {"a": 0.0, "b": 5.0, "c": 10.0}; DRND = {"r1": SMS, "r4": SMS / 4, "r20": SMS / 20}
SIZES = (0.35, 0.55)
CAPS = (2, 4, 6, 9, 19, 38); TPS = (None, 0.10); SLS = (None, 0.10, 0.20)
EXITS = [(c, tp, sl) for c in CAPS for tp in TPS for sl in SLS]; NEX = len(EXITS)
EXN = [f"c{c}_tp{'none' if tp is None else round(tp * 100)}_sl{'none' if sl is None else round(sl * 100)}" for c, tp, sl in EXITS]
MINCAPS = (4, 6, 19)
FAM = {"T1": 0, "T1t": 1, "T2": 2, "T3": 3}
WMAX = {"T1": 50, "T1t": 50, "T2": 250, "T3": 250}
FEATS = ["drop", "sell_sol", "age_s", "curve", "since_buy_s", "ndump2", "ath_r", "nbuy10", "hpct", "htype", "dev_pct", "big_pct",
         "cre_nprev", "cre_early", "cre_sell_ms"]
HX = 0.03 * SUP
G = {}

def h01(a, b):
    return (zlib.crc32(f"{a}:{b}".encode()) & 0xffffffff) / 2 ** 32

def path(Sl, Al, Bl, SOLl, TKl, Vl, Tl, FRl, SKl, n, m, a_land, size):
    """our buy right after local trade m (everything <= m is ahead of us), landing time a_land.
    -> (s_in, pnl[NEX], off[NEX], pmin[len(MINCAPS)]) or None if untradeable"""
    fr0 = FRl[m]; Vb = Vl[m]; Tb = Tl[m]
    if Vb >= UNTRADE_V: return None
    X = size * 1e9 / (1 + fr0); q = Tb * X / (Vb + X); V = Vb + X; T = Tb - q
    s_land = int(a_land // SMS); s_in = max(Sl[m], s_land); frs = fr0
    p_ref = Vb / Tb; rmin = 1e9
    cur = V * q / (T + q) * (1 - frs) / 1e9 - size
    poff = [None] * (HMAX + 2); pmn = [None] * (HMAX + 2); dn = 0
    ftp = [None] * len(TPS); fsl = [None] * len(SLS); s_cut = s_in + HMAX + 1
    for j in range(m + 1, n):
        sj = Sl[j]; pos = Al[j] - sj * SMS
        kj = 2 * sj + (1 if pos >= SELL_LAT else 0)
        while dn <= HMAX + 1 and 2 * (s_in + dn) + 1 <= kj: poff[dn] = cur; pmn[dn] = rmin; dn += 1
        if sj > s_cut or dn > HMAX + 1: break
        applied = True
        if Bl[j]:
            sol = SOLl[j]; dt = T * sol / (V + sol)
            if dt < TKl[j] / (1.0 + SKl[j]): applied = False
            else: V += sol; T -= dt
        else:
            tk = TKl[j]; so = V * tk / (T + tk); V -= so; T += tk
        if applied: frs = FRl[j]
        cur = V * q / (T + q) * (1 - frs) / 1e9 - size
        if V >= GRADV: break
        if applied:
            pr = (V / T) / p_ref
            if pr < rmin: rmin = pr
            val = (cur + size) / size
            for a in range(1, len(TPS)):
                if ftp[a] is None and val >= 1 + TPS[a]: ftp[a] = sj
            for b in range(1, len(SLS)):
                if fsl[b] is None and val <= 1 - SLS[b]: fsl[b] = sj
    while dn <= HMAX + 1: poff[dn] = cur; pmn[dn] = rmin; dn += 1
    pn = [0.0] * NEX; of = [0] * NEX
    for e, (c, tp, sl) in enumerate(EXITS):
        co = s_in + c; a = ftp[TPS.index(tp)] if tp is not None else None; b = fsl[SLS.index(sl)] if sl is not None else None
        if a is not None and a + 1 >= co: a = None
        if b is not None and b + 1 >= co: b = None
        if a is None and b is None: so_ = co
        elif b is None: so_ = a + 1
        elif a is None: so_ = b + 1
        else: so_ = min(a, b) + 1
        dd = so_ - s_in; pn[e] = poff[dd]; of[e] = dd
    return s_in, pn, of, [pmn[c] for c in MINCAPS]

def windows_for_token(t, L):
    """-> list of (fam, j_local, start, end, mode('f'/'t'), ref_fixed, feats)"""
    Sl, Al, Bl, SOLl, TKl, Vl, Tl, UIDl, MVl, WTl = L["S"], L["A"], L["B"], L["SOL"], L["TK"], L["V"], L["T"], L["UID"], L["MV"], L["WT"]
    n = len(Sl); S0 = L["S0"]; cre = L["cre"]; s_end = G["s_end"]; out = []
    bal = {}; last_buy = None; nd2 = 0; pmax = 0.0; buys_slots = []; became = set(); hold_open = {}
    for j in range(n):
        u = UIDl[j]; b = Bl[j]
        p = Vl[j] / Tl[j]
        # update state with trade j first (features are AT/after trade j)
        if b:
            bal[u] = bal.get(u, 0.0) + TKl[j]; last_buy_prev = last_buy; last_buy = Al[j]; buys_slots.append(Sl[j])
        else:
            bal[u] = bal.get(u, 0.0) - TKl[j]
        if p > pmax: pmax = p
        age = Sl[j] - S0
        k10 = bisect.bisect_left(buys_slots, Sl[j] - 9); nbuy10 = len(buys_slots) - k10
        dev_pct = bal.get(cre, 0.0) / SUP * 100 if cre is not None else 0.0
        if Sl[j] > s_end - 300: continue
        # ---- T1 / T1t triggers
        if (not b) and MVl[j] <= -2.0 and Vl[j] < UNTRADE_V and age >= 5:
            big = max(bal.values()) if bal else 0.0
            f = [-MVl[j], SOLl[j] / 1e9, age * 0.4, Vl[j] / 1e9, (Al[j] - last_buy) / 1000 if last_buy is not None else 1e9, nd2, p / pmax, nbuy10,
                 0.0, 0, dev_pct, big / SUP * 100]
            out.append((FAM["T1"], j, Al[j] + ARM, Al[j] + WMAX["T1"] * SMS, "f", p, f))
            out.append((FAM["T1t"], j, Al[j] + ARM, Al[j] + WMAX["T1t"] * SMS, "t", p, f))
        if (not b) and MVl[j] <= -2.0: nd2 += 1
        # ---- T2: big holders (first time big), window until their first sell
        if b and u not in became and Vl[j] < UNTRADE_V:
            ht = 1 if u == cre else (2 if WTl[j] == 2 else (3 if bal[u] >= HX else 0))
            if ht:
                became.add(u)
                # first sell by u after j
                je = None
                for x in range(j + 1, n):
                    if UIDl[x] == u and not Bl[x]: je = x; break
                end = min(Al[je] + 30.0 if je is not None else 1e18, Al[j] + ARM + WMAX["T2"] * SMS)
                big = max(bal.values()) if bal else 0.0
                f = [0.0, SOLl[j] / 1e9, age * 0.4, Vl[j] / 1e9, 0.0, nd2, p / pmax, nbuy10, bal[u] / SUP * 100, ht, dev_pct, big / SUP * 100]
                out.append((FAM["T2"], j, Al[j] + ARM, end, "t", p, f))
    # ---- T3: launch-phase window (one per token, from the first tape trade = the create / dev buy)
    if n and Sl[0] <= s_end - 300:
        s0b = [x for x in range(n) if Sl[x] == S0 and Bl[x]]
        dev_sol = sum(SOLl[x] for x in s0b if UIDl[x] == cre) / 1e9
        bun = [x for x in s0b if UIDl[x] != cre]; jx = s0b[-1] if s0b else 0
        bal0 = {}
        for x in s0b: bal0[UIDl[x]] = bal0.get(UIDl[x], 0.0) + TKl[x]
        f = [0.0, dev_sol, 0.0, Vl[jx] / 1e9, 0.0, 0, 1.0, len(set(UIDl[x] for x in bun)), sum(TKl[x] for x in bun) / SUP * 100, 0,
             bal0.get(cre, 0.0) / SUP * 100, (max(bal0.values()) / SUP * 100) if bal0 else 0.0]
        out.append((FAM["T3"], 0, Al[0] + ARM, Al[0] + ARM + WMAX["T3"] * SMS, "t", Vl[0] / Tl[0], f))
    return out

def work(toks):
    d = G["d"]; R = dict(W=[], F=[], P=[])
    for t in toks:
        o = int(d["off"][t]); n = int(d["cnt"][t])
        if n < 5: continue
        sl = slice(o, o + n)
        L = dict(S=d["s"][sl].tolist(), A=d["arr"][sl].tolist(), B=d["buy"][sl].astype(bool).tolist(), SOL=d["sol"][sl].tolist(),
                 TK=d["tokn"][sl].tolist(), V=d["vsol"][sl].tolist(), T=d["vtok"][sl].tolist(), FR=d["fr"][sl].astype(float).tolist(),
                 SK=d["slack"][sl].astype(float).tolist(), UID=d["uid"][sl].tolist(), MV=d["move"][sl].tolist(), WT=d["wt"][sl].tolist(),
                 S0=d["meta"][t]["S0"], cre=(C.crc(d["meta"][t]["creator"]) if d["meta"][t].get("creator") else None))
        W = windows_for_token(t, L)
        if not W: continue
        ch = G["crehist"].get(d["meta"][t]["m"], [0, 0, ""]); cu = L["cre"]
        csell = [L["A"][x] for x in range(n) if cu is not None and L["UID"][x] == cu and not L["B"][x]]
        W2 = []
        for (fam, j, st, en, mode, pref, f) in W:
            k = bisect.bisect_left(csell, st)
            W2.append((fam, j, st, en, mode, pref, f + [ch[0], (ch[1] / ch[0]) if ch[0] else -1.0, (csell[k] - st) if k < len(csell) else 1e9]))
        W = W2
        A = np.array(L["A"]); P = d["vsol"][sl] / d["vtok"][sl]
        rix = np.searchsorted(A, A - LREF, side="right") - 1          # trailing reference index (price known LREF before x)
        p_first = d["ppre"][o]
        REF = np.where(rix >= 0, P[np.maximum(rix, 0)], p_first); RAT = P / REF
        Al = L["A"]; Sl = L["S"]; cache = {}
        for (fam, j, st, en, mode, pref, f) in W:
            wid = len(R["W"]); R["W"].append((fam, t, o + j, st, en, f))
            i0 = bisect.bisect_left(Al, st); iE = bisect.bisect_left(Al, en)
            if i0 >= n: continue
            for yi, y in enumerate(YS):
                if mode == "f":
                    lim = pref * (1 - y)
                    pre_ok = P[i0 - 1] <= lim                                  # already below the limit when we go live
                    cand = np.flatnonzero(P[i0:iE] <= lim) + i0
                else:
                    pre_ok = False
                    cand = np.flatnonzero(RAT[i0:iE] <= 1 - y) + i0
                if not pre_ok and len(cand) == 0: continue
                for di, dm in enumerate(DMOD):
                    hit = None
                    if pre_ok:
                        m = i0 - 1; a_land = st; hit = (m, m, a_land)
                    else:
                        for x in cand.tolist():
                            D = DFIX[dm] if dm in DFIX else h01(f"{o + j}.{fam}.{di}", o + x) * DRND[dm]
                            a_land = Al[x] + D
                            if a_land >= en: break
                            m = bisect.bisect_right(Al, a_land) - 1
                            limx = lim if mode == "f" else REF[x] * (1 - y)
                            if P[m] <= limx: hit = (x, m, a_land); break
                    if hit is None: continue
                    x, m, a_land = hit
                    key = (m, int(a_land // SMS))
                    pid = cache.get(key)
                    if pid is None:
                        outs = [path(L["S"], L["A"], L["B"], L["SOL"], L["TK"], L["V"], L["T"], L["FR"], L["SK"], n, m, a_land, sz) for sz in SIZES]
                        if outs[0] is None: pid = -1
                        else:
                            pid = len(R["P"]); R["P"].append((o + m, outs[0][0], [o_[1] for o_ in outs], [o_[2] for o_ in outs], outs[0][3]))
                        cache[key] = pid
                    if pid < 0: continue
                    R["F"].append((wid, yi, di, o + x, o + m, a_land, pid))
    return R

def main(day, procs):
    t0 = time.time()
    d = C.load(day); G["d"] = d; G["s_end"] = int(d["s"].max())
    G["crehist"] = json.load(open(f"{C.OUT}/crehist.json"))
    nt = len(d["meta"]); toks = list(range(nt)); chunks = [toks[i::procs * 6] for i in range(procs * 6)]
    W = []; F = []; P = []
    with get_context("fork").Pool(procs) as pool:
        for k, R in enumerate(pool.imap_unordered(work, chunks)):
            w0 = len(W); p0 = len(P)
            W += R["W"]; P += R["P"]
            F += [(a + w0, b, c, e, f, g, h + p0) for (a, b, c, e, f, g, h) in R["F"]]
            print(f"  chunk {k + 1}/{len(chunks)}: windows {len(W)}, fills {len(F)}, paths {len(P)}, {time.time() - t0:.0f} s", flush=True)
    Wa = dict(w_fam=np.array([x[0] for x in W], np.int8), w_tok=np.array([x[1] for x in W], np.int32), w_j=np.array([x[2] for x in W], np.int64),
              w_start=np.array([x[3] for x in W]), w_end=np.array([x[4] for x in W]), w_f=np.array([x[5] for x in W], np.float32))
    Fa = np.array(F, np.float64) if F else np.zeros((0, 7))
    Pa = dict(p_m=np.array([x[0] for x in P], np.int64), p_sin=np.array([x[1] for x in P], np.int64),
              p_pnl=np.array([x[2] for x in P], np.float32), p_off=np.array([x[3] for x in P], np.int8), p_min=np.array([x[4] for x in P], np.float32))
    fx = Fa[:, 3].astype(np.int64)
    np.savez_compressed(f"{C.OUT}/ps4_{day}.npz", **Wa, f_w=Fa[:, 0].astype(np.int32), f_y=Fa[:, 1].astype(np.int8), f_d=Fa[:, 2].astype(np.int8),
             f_x=fx.astype(np.int32), f_m=Fa[:, 4].astype(np.int32), f_D=(Fa[:, 5] - d["arr"][fx]).astype(np.float32), f_pid=Fa[:, 6].astype(np.int32), **Pa)
    json.dump(dict(ys=YS, dmod=DMOD, sizes=SIZES, exits=EXN, mincaps=MINCAPS, fam=FAM, wmax=WMAX, feats=FEATS, arm=ARM, lref=LREF, hx=HX / SUP),
              open(f"{C.OUT}/ps4_meta.json", "w"))
    print(f"{day}: windows {len(W)} ({np.bincount(Wa['w_fam'], minlength=4).tolist()}), fills {len(F)}, paths {len(P)}, {time.time() - t0:.0f} s", flush=True)

if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 3)
