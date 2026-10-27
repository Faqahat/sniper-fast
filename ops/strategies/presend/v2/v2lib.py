#!/usr/bin/env python3
# PRE-SEND V2 replay, step 1 (read-only, $0): windows + fills + exit paths per tape day, with the LANDING CALIBRATED to the live
# probe (c3_model.json). Mechanics are the study's (ps4_replay.py), unchanged where not stated:
#  - tape = successful curve trades in chain order; block-position clock A (slot x 212 ms + index share);
#  - trailing reference = the price LREF (50) ms before the crossing; a crossing = a trade at <= ref x (1 - y);
#  - after a fill: ps4.path() mechanics (our buy after trade m; followers whose slippage our buy breaks are dropped; pump fee both
#    sides; sells land 75 ms into the exit slot; TP / SL = sell in the slot after the first slot that reaches it), here for
#    4 sizes and a 48-exit grid (time 1-4 slots x TP none/5/10/15% x SL none/10/20%).
# Landing rows:
#  "c"  = the study's +10 ms (20 attempts per slot), and "r4" = the study's U(0, 53) ms (both keep the study's rule a_land < end);
#  "L<k>" = CALIBRATED: k attempts per slot, attempts sent from the window start; per dump: P(no attempt could fill) and the
#          landing delay D are drawn from the probe-calibrated attempt model (c3: P(none | k, time since the window went live),
#          D quantiles x DSCALE = block clock / first-sighting clock, 0.85 measured on the probe); an attempt in flight may land
#          after the window end (live: in-flight attempts still fill), the CROSSING must be inside the window;
#          on a miss (none, or the price back above the limit at the landing) the next crossing must come after the landing
#          (or 50 ms after the dump): one draw per dump, not per trade;  "L<k>d2" = deadline +2 slots instead of +1.
# Families (one window per trigger; v2eng applies W, filters, per-token arming, servers, leader filters and costs):
#  T2  : the study's whale buy (first >= 3% holding, any wallet type) -> until its first sell + 30 ms, <= 250 slots;
#        + flags: create-slot trigger, seller-tool history on the token, trigger is a rebuy
#  CD  : creator-dump targeting (the pre-senders' target): one window per token from the create, <= 250 slots, with the
#        creator's CAUSAL launch history (crehist_v2.json: previous launches, early dumps, big early dumps)
#  T1t : the study's trailing variant after a >= 4.65% dump on a serial-creator token (<= 50 slots)
# usage: nice python3 v2lib.py R2 [procs]  -> presend_v2/v2_<day>.npz + _meta.json
import sys, os, json, bisect, zlib, time
import numpy as np
from multiprocessing import get_context
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import v2data as V

SMS = 212.0; SELL_LAT = 75.0; GRADV = 110e9; UNTRADE_V = 100e9; SUP = 1e15; HX = 0.03 * SUP
ARM = 50.0; LREF = float(os.environ.get("PSV2_LREF", "50")); DSCALE = 0.85
TAG = os.environ.get("PSV2_TAG", "")      # sensitivity runs write v2_<day><TAG>.npz
# PSV2_DROP = a JSON list of wallets whose BUYS after our entry are removed from the tape (the cohort test: "nocw" = the 541
# consistent-winner bots of ops/overnight/dip/drop_cw.json; memory: always report the cohort-removed variant)
DROP = set()
if os.environ.get("PSV2_DROP"):
    import zlib as _z
    DROP = {_z.crc32(w.encode()) for w in json.load(open(os.environ["PSV2_DROP"]))}
if os.environ.get("PSV2_DROP_UIDS"):          # the control: a list of tape uids (activity-matched random wallets)
    DROP = set(int(u) for u in json.load(open(os.environ["PSV2_DROP_UIDS"])))
# PSV2_NAIVE=1: no follower is dropped (every later buy happens as recorded, whatever our buy did to the price). The gap to the
# normal run = what the follower crowd-out model (generic slippage slack, INFERRED) takes off; the rest of the size effect is
# our own buy's price impact on the real tape (curve math)
NAIVE = os.environ.get("PSV2_NAIVE") == "1"
YS = (0.08, 0.12, 0.16)
ROWS = [("c", "fix", 10.0), ("r4", "rnd", SMS / 4), ("L2", "dl1", 2.0), ("L4", "dl1", 4.0), ("L8", "dl1", 8.0), ("L12", "dl1", 12.0),
        ("L20", "dl1", 20.0), ("L4d2", "dl2", 4.0), ("L8d2", "dl2", 8.0), ("P", "dl1", 3.79),
        ("L4x", "dl1x", 4.0), ("L8x", "dl1x", 8.0), ("L12x", "dl1x", 12.0), ("L20x", "dl1x", 20.0)]
# "x" rows = PESSIMISTIC landing: the probe's extra misses kept at every rate (P(none) -> 1 - (1 - none) x 0.90: measured 26.6% vs
# model 18.4% at 3.79 / slot) and D not shrunk to the block clock (x 1.0 instead of 0.85)
RN = [r[0] for r in ROWS]
SIZES = (0.2, 0.35, 0.55, 1.0, 1.5, 0.75)        # 0.75 appended last (10-25 size sweep) so older indices stay valid
CAPS = (1, 2, 3, 4); TPS = (None, 0.05, 0.10, 0.15); SLS = (None, 0.10, 0.20)
EXITS = [(c, tp, sl) for c in CAPS for tp in TPS for sl in SLS]; NEX = len(EXITS)
EXN = [f"c{c}_tp{'none' if tp is None else round(tp * 100)}_sl{'none' if sl is None else round(sl * 100)}" for c, tp, sl in EXITS]
HMAX = max(CAPS)
FAM = {"T2": 0, "CD": 1, "T1t": 2}
WMAX = {"T2": 250, "CD": 250, "T1t": 50}
FEATS = ["hpct", "htype", "cslot", "age_s", "curve", "wsol", "dev_pct", "big_pct", "nbuy10", "ath_r", "nd2", "tool_n", "trig_rebuy",
         "cre_nprev", "cre_early", "cre_big", "cre_sell_ms", "drop", "sell_sol", "first", "hour", "slot"]
FI = {k: i for i, k in enumerate(FEATS)}
FFEATS = ["D", "xdrop", "x_whale", "x_cre", "x_tool", "n_between", "cls_in", "cls_x", "el", "pref"]
G = {}

def h01(*a):
    return (zlib.crc32(":".join(str(x) for x in a).encode()) & 0xffffffff) / 2 ** 32

def model():
    if "M" in G: return G["M"]
    M = json.load(open(f"{V.OUT}/c3_model.json")); G["M"] = M
    return M

def draw(kind, k, el, u1, u2):
    """-> None (no attempt could fill this dump) or D ms (block clock)"""
    M = model(); els = M["els"]
    e = els[max(0, bisect.bisect_right(els, el) - 1)]
    pess = kind.endswith("x"); kind = kind.rstrip("x")
    g = M["grid"][f"{kind}|{float(k)}|{e}"]
    none = 1 - (1 - g["none"]) * 0.90 if pess else g["none"]
    if u1 < none: return None
    q = g["q"]; x = u2 * 100.0; i = min(int(x), 99); f = x - i
    return (1.0 if pess else DSCALE) * (q[i] + (q[i + 1] - q[i]) * f)

def path(L, n, m, a_land, size):
    """ps4_replay.path for the V2 exit grid: our buy right after local trade m at a_land -> (s_in, pnl[NEX], off[NEX], pmin) or None"""
    Sl, Al, Bl, SOLl, TKl, Vl, Tl, FRl, SKl = L["S"], L["A"], L["B"], L["SOL"], L["TK"], L["V"], L["T"], L["FR"], L["SK"]
    UIDl = L.get("UID") if DROP else None
    fr0 = FRl[m]; Vb = Vl[m]; Tb = Tl[m]
    if Vb >= UNTRADE_V: return None
    X = size * 1e9 / (1 + fr0); q = Tb * X / (Vb + X); Vv = Vb + X; Tt = Tb - q
    s_land = int(a_land // SMS); s_in = max(Sl[m], s_land); frs = fr0
    p_ref = Vb / Tb; rmin = 1e9
    cur = Vv * q / (Tt + q) * (1 - frs) / 1e9 - size
    poff = [None] * (HMAX + 2); pmn = [None] * (HMAX + 2); dn = 0
    ftp = [None] * len(TPS); fsl = [None] * len(SLS); s_cut = s_in + HMAX + 1
    for j in range(m + 1, n):
        sj = Sl[j]; pos = Al[j] - sj * SMS
        kj = 2 * sj + (1 if pos >= SELL_LAT else 0)
        while dn <= HMAX + 1 and 2 * (s_in + dn) + 1 <= kj: poff[dn] = cur; pmn[dn] = rmin; dn += 1
        if sj > s_cut or dn > HMAX + 1: break
        if UIDl is not None and Bl[j] and UIDl[j] in DROP: continue          # cohort test: that wallet's buy never happened
        applied = True
        if Bl[j]:
            sol = SOLl[j]; dt = Tt * sol / (Vv + sol)
            if dt < TKl[j] / (1.0 + SKl[j]) and not NAIVE: applied = False
            else: Vv += sol; Tt -= dt
        else:
            tk = TKl[j]; so = Vv * tk / (Tt + tk); Vv -= so; Tt += tk
        if applied: frs = FRl[j]
        cur = Vv * q / (Tt + q) * (1 - frs) / 1e9 - size
        if Vv >= GRADV: break
        if applied:
            pr = (Vv / Tt) / p_ref
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
    return s_in, pn, of, pmn[2]

def windows_for_token(L, meta, ch):
    """-> list of (fam, j, start, end, feats)"""
    Sl, Al, Bl, SOLl, TKl, Vl, Tl, UIDl, MVl, WTl, Il = (L[k] for k in ("S", "A", "B", "SOL", "TK", "V", "T", "UID", "MV", "WT", "I"))
    n = len(Sl); S0 = meta["S0"]; cre = L["cre"]; s_end = G["s_end"]; out = []
    bal = {}; last_buy = None; nd2 = 0; pmax = 0.0; buys_slots = []; became = set(); tool_n = 0
    for j in range(n):
        u = UIDl[j]; b = Bl[j]; p = Vl[j] / Tl[j]
        rebuy = False
        if b:
            bal[u] = bal.get(u, 0.0) + TKl[j]; last_buy = Al[j]; buys_slots.append(Sl[j])
            # seller-tool pattern (feed-observable): a buy 1-3 block positions after a >= 0.3 SOL sell that moved the price <= -4%
            # in the same slot, by another wallet, the buys since that sell = 25-110% of its SOL
            k = j - 1; acc = SOLl[j]
            while k >= 0 and Sl[k] == Sl[j] and Il[j] - Il[k] <= 3:
                if not Bl[k]:
                    if UIDl[k] != u and SOLl[k] >= 0.3e9 and MVl[k] <= -4.0 and 0.25 * SOLl[k] <= acc <= 1.10 * SOLl[k]: rebuy = True
                    break
                acc += SOLl[k]; k -= 1
            if rebuy: tool_n += 1
        else:
            bal[u] = bal.get(u, 0.0) - TKl[j]
        if p > pmax: pmax = p
        age = Sl[j] - S0
        if Sl[j] > s_end - 300: continue
        # ---- T1t (the study's selected filter only: drop >= 4.65%, serial creator; sell size and first-dump as features)
        if (not b) and MVl[j] <= -4.65 and Vl[j] < UNTRADE_V and age >= 5 and ch[0] >= 3 and ch[0] and ch[1] / ch[0] >= 0.8:
            big = max(bal.values()) if bal else 0.0
            f = dict(drop=-MVl[j], sell_sol=SOLl[j] / 1e9, age_s=age * SMS / 1000, curve=Vl[j] / 1e9, first=1.0 if nd2 == 0 else 0.0, nd2=nd2,
                     ath_r=p / pmax, tool_n=tool_n, big_pct=big / SUP * 100)
            out.append((FAM["T1t"], j, Al[j] + ARM, Al[j] + WMAX["T1t"] * SMS, f))
        if (not b) and MVl[j] <= -2.0: nd2 += 1
        # ---- T2
        if b and u not in became and Vl[j] < UNTRADE_V:
            ht = 1 if u == cre else (2 if WTl[j] == 2 else (3 if bal[u] >= HX else 0))
            if ht:
                became.add(u)
                je = None
                for x in range(j + 1, n):
                    if UIDl[x] == u and not Bl[x]: je = x; break
                end = min(Al[je] + 30.0 if je is not None else 1e18, Al[j] + ARM + WMAX["T2"] * SMS)
                big = max(bal.values()) if bal else 0.0
                k10 = bisect.bisect_left(buys_slots, Sl[j] - 9)
                f = dict(hpct=bal[u] / SUP * 100, htype=ht, cslot=1.0 if Sl[j] == S0 else 0.0, age_s=age * SMS / 1000, curve=Vl[j] / 1e9,
                         wsol=SOLl[j] / 1e9, dev_pct=(bal.get(cre, 0.0) / SUP * 100) if cre is not None else 0.0, big_pct=big / SUP * 100,
                         nbuy10=len(buys_slots) - k10, ath_r=p / pmax, nd2=nd2, tool_n=tool_n, trig_rebuy=1.0 if rebuy else 0.0, whale=u)
                out.append((FAM["T2"], j, Al[j] + ARM, end, f))
    # ---- CD: one window per token from the first tape trade (the create / dev buy)
    if n and Sl[0] <= s_end - 300:
        out.append((FAM["CD"], 0, Al[0] + ARM, Al[0] + ARM + WMAX["CD"] * SMS, dict(age_s=0.0, curve=Vl[0] / 1e9)))
    for (fam, j, st, en, f) in out:
        f["cre_nprev"] = ch[0]; f["cre_early"] = (ch[1] / ch[0]) if ch[0] else -1.0; f["cre_big"] = (ch[2] / ch[0]) if ch[0] else -1.0
        f["slot"] = Sl[j]
    return out

def work(toks):
    d = G["d"]; R = dict(W=[], F=[], P=[])
    s0c, cls = G["lc"]
    for t in toks:
        o = int(d["off"][t]); n = int(d["cnt"][t])
        if n < 5: continue
        sl = slice(o, o + n); meta = d["meta"][t]
        L = dict(S=d["s"][sl].tolist(), A=d["arr"][sl].tolist(), B=d["buy"][sl].astype(bool).tolist(), SOL=d["sol"][sl].tolist(),
                 TK=d["tokn"][sl].tolist(), V=d["vsol"][sl].tolist(), T=d["vtok"][sl].tolist(), FR=d["fr"][sl].astype(float).tolist(),
                 SK=d["slack"][sl].astype(float).tolist(), UID=d["uid"][sl].tolist(), MV=d["move"][sl].tolist(), WT=d["wt"][sl].tolist(),
                 I=d["i"][sl].tolist(), T0=int(d["t"][o]), cre=(V.crc(meta["creator"]) if meta.get("creator") else None))
        ch = G["crehist"].get(meta["m"], [0, 0, 0, ""])
        W = windows_for_token(L, meta, ch)
        if not W: continue
        cu = L["cre"]
        csell = [L["A"][x] for x in range(n) if cu is not None and L["UID"][x] == cu and not L["B"][x]]
        A = np.array(L["A"]); P = d["vsol"][sl] / d["vtok"][sl]
        rix = np.searchsorted(A, A - LREF, side="right") - 1
        REF = np.where(rix >= 0, P[np.maximum(rix, 0)], d["ppre"][o]); RAT = P / REF
        Al = L["A"]; Sl = L["S"]; cache = {}
        for (fam, j, st, en, f) in W:
            kc = bisect.bisect_left(csell, st); f["cre_sell_ms"] = (csell[kc] - st) if kc < len(csell) else 1e9
            whale = f.pop("whale", None); f["hour"] = ((int(d["t"][o + j]) + 5 * 3600) // 3600) % 24
            wid = len(R["W"]); R["W"].append((fam, t, o + j, st, en, [float(f.get(k, 0.0)) for k in FEATS]))
            i0 = bisect.bisect_left(Al, st); iE = bisect.bisect_left(Al, en)
            if i0 >= n: continue
            for yi, y in enumerate(YS):
                cand = (np.flatnonzero(RAT[i0:iE] <= 1 - y) + i0).tolist()
                if not cand: continue
                for ri, (rn, kind, par) in enumerate(ROWS):
                    hit = None; skip_until = -1e18
                    for x in cand:
                        if kind in ("fix", "rnd"):
                            D = par if kind == "fix" else h01(o + j, fam, ri, o + x) * par
                            a_land = Al[x] + D
                            if a_land >= en: break
                        else:                                     # calibrated rows (dl1 / dl2 / dl1x)
                            if Al[x] < skip_until: continue
                            el = Al[x] - st
                            D = draw(kind, par, el, h01("n", o + j, fam, o + x), h01("d", o + j, fam, o + x))    # common random numbers across rows
                            if D is None: skip_until = Al[x] + LREF; continue
                            a_land = Al[x] + D
                        m = bisect.bisect_right(Al, a_land) - 1
                        if P[m] <= REF[x] * (1 - y): hit = (x, m, a_land, D); break
                        skip_until = max(a_land, Al[x] + LREF)
                    if hit is None: continue
                    x, m, a_land, D = hit
                    key = (m, int(a_land // SMS))
                    pid = cache.get(key)
                    if pid is None:
                        outs = [path(L, n, m, a_land, sz) for sz in SIZES]
                        if outs[0] is None: pid = -1
                        else:
                            pid = len(R["P"]); R["P"].append((o + m, outs[0][0], [z[1] for z in outs], [z[2] for z in outs], outs[0][3]))
                        cache[key] = pid
                    if pid < 0: continue
                    # fill features: the crossing's own drop, seller = the T2 whale / the creator, a rebuy 1-3 positions after the
                    # crossing (seller tool), trades between the crossing and us, leader class of the entry slot and the crossing slot
                    xd = -L["MV"][x] if not L["B"][x] else 0.0
                    xt = 0.0
                    for k2 in range(x + 1, min(n, x + 4)):
                        if Sl[k2] != Sl[x] or L["I"][k2] - L["I"][x] > 3: break
                        if L["B"][k2] and L["UID"][k2] != L["UID"][x]: xt = 1.0; break
                    s_in = R["P"][pid][1]
                    ci = s_in - s0c; cx = Sl[x] - s0c
                    ff = [D, xd, 1.0 if (whale is not None and L["UID"][x] == whale) else 0.0, 1.0 if (cu is not None and L["UID"][x] == cu) else 0.0,
                          xt, float(m - x), float(cls[ci]) if 0 <= ci < len(cls) else 0.0, float(cls[cx]) if 0 <= cx < len(cls) else 0.0,
                          Al[x] - st, float(REF[x])]
                    R["F"].append((wid, yi, ri, o + x, o + m, a_land, pid, ff))
    return R

def main(day, procs):
    t0 = time.time()
    d = V.load_day(day); G["d"] = d; G["s_end"] = int(d["s"].max())
    G["crehist"] = json.load(open(f"{V.OUT}/crehist_v2.json")); G["lc"] = V.leader_classes(); model()
    nt = len(d["meta"]); toks = list(range(nt)); chunks = [toks[i::procs * 8] for i in range(procs * 8)]
    W = []; F = []; P = []
    with get_context("fork").Pool(procs) as pool:
        for k, R in enumerate(pool.imap_unordered(work, chunks)):
            w0 = len(W); p0 = len(P)
            W += R["W"]; P += R["P"]
            F += [(a + w0, b, c, e, f_, g, h + p0, ff) for (a, b, c, e, f_, g, h, ff) in R["F"]]
            if (k + 1) % 8 == 0: print(f"  {day} chunk {k + 1}/{len(chunks)}: windows {len(W)}, fills {len(F)}, paths {len(P)}, {time.time() - t0:.0f} s", flush=True)
    fx = np.array([x[3] for x in F], np.int64)
    np.savez_compressed(f"{V.OUT}/v2_{day}{TAG}.npz",
        w_fam=np.array([x[0] for x in W], np.int8), w_tok=np.array([x[1] for x in W], np.int32), w_j=np.array([x[2] for x in W], np.int64),
        w_start=np.array([x[3] for x in W]), w_end=np.array([x[4] for x in W]), w_f=np.array([x[5] for x in W], np.float64),
        f_w=np.array([x[0] for x in F], np.int32), f_y=np.array([x[1] for x in F], np.int8), f_r=np.array([x[2] for x in F], np.int8),
        f_x=fx, f_m=np.array([x[4] for x in F], np.int64), f_land=np.array([x[5] for x in F]), f_pid=np.array([x[6] for x in F], np.int32),
        f_f=np.array([x[7] for x in F], np.float64).reshape(-1, len(FFEATS)),
        p_m=np.array([x[0] for x in P], np.int64), p_sin=np.array([x[1] for x in P], np.int64),
        p_pnl=np.array([x[2] for x in P], np.float32).reshape(-1, len(SIZES), NEX), p_off=np.array([x[3] for x in P], np.int8).reshape(-1, len(SIZES), NEX),
        p_min=np.array([x[4] for x in P], np.float32))
    if not TAG: json.dump(dict(ys=YS, rows=ROWS, sizes=SIZES, exits=EXN, fam=FAM, wmax=WMAX, feats=FEATS, ffeats=FFEATS, arm=ARM, lref=LREF, dscale=DSCALE),
              open(f"{V.OUT}/v2_meta.json", "w"))
    print(f"{day}: windows {len(W)} ({np.bincount([x[0] for x in W], minlength=3).tolist()}), fills {len(F)}, paths {len(P)}, {time.time() - t0:.0f} s", flush=True)

if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 5)
