#!/usr/bin/env python3
# PRE-SEND V2 replay, step 2 (read-only): engine + REAL costs on the v2lib windows / fills / paths of a day.
# Per config: windows of one family passing a filter -> one armed window per token at a time (a fill blocks the token until our
# sell + 300 ms) -> `servers` servers with one position each (live probe: 1 server, one position; while every server holds a
# position nothing is sent and nothing fills) -> optional leader filter (send only while the leader is of an allowed client
# class: a fill counts only if it lands in an allowed slot, attempts are charged only for allowed armed slots) -> costs:
#   real (MEASURED on the probe): every attempt that does not fill = 5,120 lamports (5,000 + 120k CU x 1,000 uL); a fill =
#        buy 5,120 + tip 200,000; its sell = fee 605,000 + fan-out tips 1,200,000  -> 2,010,120 lamports fixed per fill;
#   cheapsell (INFERRED option, a sell-path change = owner's OK): the sell with one 0.0002 tip and 5,000 + 120k x 10k uL priority.
# Calibrated rows (L*, P): the crossing must be inside the window, an in-flight attempt may land after it. Study rows (c, r4):
# the study's rule (landing inside the window).
import sys, os, json, bisect
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import v2data as V
SMS = 212.0; MARGIN = 300.0
M = json.load(open(f"{V.OUT}/v2_meta.json"))
EXN = M["exits"]; EXI = {k: i for i, k in enumerate(EXN)}; YS = M["ys"]; ROWS = [tuple(r) for r in M["rows"]]; RN = [r[0] for r in ROWS]
SIZES = M["sizes"]; FI = {k: i for i, k in enumerate(M["feats"])}; FFI = {k: i for i, k in enumerate(M["ffeats"])}
KROW = {r[0]: (20.0 if r[0] == "c" else float(r[2]) if r[1] != "rnd" else 4.0) for r in ROWS}
LAM = 1e-9
COST = {"real": dict(att=5120 * LAM, fill=(5120 + 200_000 + 605_000 + 1_200_000) * LAM),
        "cheapsell": dict(att=5120 * LAM, fill=(5120 + 200_000 + 5_000 + 120_000 * 10_000 / 1e6 + 200_000) * LAM),
        "study": dict(att=(5000 + 60_000 * 1_000 / 1e6) * LAM, fill=(0.001 + 2 * (5000 + 60) * LAM))}

def load(day):
    z = np.load(f"{V.OUT}/v2_{day}{os.environ.get('PSV2_TAG', '')}.npz"); D = {k: z[k] for k in z.files}
    tp = V.load_day(day, cols=("s", "arr", "bt", "tok"))
    D["day"] = day; D["arr"] = tp["arr"]; D["s_tape"] = tp["s"]
    D["w_t"] = tp["t"][D["w_j"]]; D["w_in"] = V.in_win(day, D["w_t"])
    D["f_xa"] = tp["arr"][D["f_x"]]
    nW = len(D["w_fam"]); D["nW"] = nW
    FR = np.full((len(YS), len(ROWS), nW), -1, np.int64)
    FR[D["f_y"], D["f_r"], D["f_w"]] = np.arange(len(D["f_w"]))
    D["FR"] = FR; D["hours"] = V.hours(day)
    s0, c = V.leader_classes(); D["lc_s0"] = s0; D["lc"] = c
    # per class cumulative slot counts (for charging only allowed slots)
    D["lc_cum"] = {k: np.concatenate([[0], np.cumsum(c == k)]) for k in range(len(V.CLS))}
    D["w_cls_known"] = np.isin(V.slot_class(D["s_tape"][D["w_j"]]), np.arange(1, len(V.CLS)))
    return D

def wf(D, k): return D["w_f"][:, FI[k]]

def allowed_slots(D, s_a, s_b, allowed):
    """number of slots in [s_a, s_b] whose leader class is allowed (vectorised)"""
    s0 = D["lc_s0"]; n = len(D["lc"])
    a = np.clip(s_a - s0, 0, n); b = np.clip(s_b - s0 + 1, 0, n)
    tot = np.zeros(len(s_a))
    for k in allowed: tot += D["lc_cum"][k][b] - D["lc_cum"][k][a]
    return tot

def run(D, wmask, W, y, row, size, ex, end_cre=False, servers=1, allowed=None, cost="real", k=None, detail=False, busy_pause=True):
    yi = YS.index(y); ri = RN.index(row); si = SIZES.index(size); e = EXI[ex] if isinstance(ex, str) else ex
    k = KROW[row] if k is None else k; C = COST[cost] if isinstance(cost, str) else cost
    idx = np.flatnonzero(wmask & D["w_in"])
    z = dict(pnl=0.0, fill=0, armed=0, att=0.0, gross=0.0, cost_att=0.0, cost_fill=0.0, per_fill=0.0, gross_per_fill=0.0, winr=0.0, skip=0,
             att_per_fill=float("inf"), armed_slots=0.0, k=k, fill_rate=0.0)
    if len(idx) == 0: return z
    st = D["w_start"][idx]; en = np.minimum(D["w_end"][idx], st + W * SMS)
    if end_cre: en = np.minimum(en, st + D["w_f"][idx, FI["cre_sell_ms"]] + 30.0)
    fr = D["FR"][yi, ri, idx]; has = fr >= 0; frr = np.maximum(fr, 0)
    xa = np.where(has, D["f_xa"][frr], np.inf); land = np.where(has, D["f_land"][frr], np.inf)
    cal = ROWS[ri][1] in ("dl1", "dl2", "dl1x")
    valid = has & ((xa < en) if cal else (land < en))
    if allowed is not None:
        ci = D["f_f"][frr, FFI["cls_in"]].astype(int)
        valid &= np.isin(ci, list(allowed))
    pid = np.where(valid, D["f_pid"][frr], -1); pp = np.maximum(pid, 0)
    sin = np.where(valid, D["p_sin"][pp], 0)
    off = np.where(valid, D["p_off"][pp, si, e], 0).astype(np.int64)
    pn = np.where(valid, D["p_pnl"][pp, si, e], 0.0)
    xt = (sin + off) * SMS + 75.0
    ft = np.where(valid, land, np.inf)
    tok = D["w_tok"][idx]
    # one armed window per token at a time; a fill blocks the token until our sell + MARGIN; the stream stops at the fill
    o = np.lexsort((st, tok)); armed = np.zeros(len(idx), bool); aend = np.zeros(len(idx))
    last_tok = -1; free_at = -np.inf
    for r in o.tolist():
        t = tok[r]
        if t != last_tok: last_tok = t; free_at = -np.inf
        if st[r] < free_at: continue
        armed[r] = True
        if valid[r]: aend[r] = min(ft[r], en[r]); free_at = xt[r] + MARGIN       # the stream stops when our fill lands (or at the window end)
        else: aend[r] = en[r]; free_at = en[r]
    fills = np.flatnonzero(armed & valid); fills = fills[np.argsort(ft[fills], kind="stable")]
    busy = [-np.inf] * servers; acc = []; skip = 0; ivs = []
    for r in fills.tolist():
        t0 = ft[r]
        sv = min(range(servers), key=lambda s_: busy[s_])
        if busy[sv] > t0: skip += 1; continue
        busy[sv] = xt[r] + MARGIN; acc.append(r); ivs.append((sv, t0, busy[sv]))
    # all-busy intervals: attempts paused
    bb = []
    if busy_pause and ivs:
        per = [sorted((a, b) for s_, a, b in ivs if s_ == q) for q in range(servers)]
        if servers == 1: bb = per[0]
        else:
            A_, B_ = per[0], per[1]; i = j = 0
            while i < len(A_) and j < len(B_):
                lo = max(A_[i][0], B_[j][0]); hi = min(A_[i][1], B_[j][1])
                if lo < hi: bb.append((lo, hi))
                if A_[i][1] < B_[j][1]: i += 1
                else: j += 1
    ar = np.flatnonzero(armed)
    a0 = st[ar]; a1 = np.maximum(aend[ar], a0)
    dur = a1 - a0
    if bb:
        bbs = np.array([x[0] for x in bb]); bbe = np.array([x[1] for x in bb]); cum = np.concatenate([[0.0], np.cumsum(bbe - bbs)])
        def ov(a, b):
            i0 = bisect.bisect_right(bbe, a); i1 = bisect.bisect_left(bbs, b)
            if i1 <= i0: return 0.0
            tot = cum[i1] - cum[i0]
            tot -= max(0.0, a - bbs[i0]) if i0 < len(bbs) else 0.0
            tot -= max(0.0, bbe[i1 - 1] - b) if i1 - 1 >= 0 else 0.0
            return max(tot, 0.0)
        dur = np.array([max(dd - ov(a, b), 0.0) for dd, a, b in zip(dur.tolist(), a0.tolist(), a1.tolist())])
    slots = np.maximum(np.ceil(dur / SMS), 1.0)
    if allowed is not None:
        sa = (a0 // SMS).astype(np.int64); sb = (a1 // SMS).astype(np.int64)
        nal = allowed_slots(D, sa, sb, allowed); ntot = (sb - sa + 1).astype(float)
        slots = slots * nal / np.maximum(ntot, 1.0)
    att = float(k * slots.sum())
    acc = np.array(acc, np.int64); nf = len(acc)
    gross = float(pn[acc].sum()) if nf else 0.0
    cost_fill = nf * C["fill"]; cost_att = max(att - nf, 0.0) * C["att"]
    pnl = gross - cost_fill - cost_att
    per = (pn[acc] - C["fill"]) if nf else np.zeros(0)
    out = dict(pnl=pnl, fill=nf, armed=int(armed.sum()), att=att, gross=gross, cost_att=cost_att, cost_fill=cost_fill,
               per_fill=pnl / nf if nf else 0.0, gross_per_fill=gross / nf if nf else 0.0, winr=float((per > 0).mean()) if nf else 0.0, skip=skip,
               att_per_fill=att / nf if nf else float("inf"), armed_slots=float(slots.sum()), k=k, fill_rate=nf / max(int(armed.sum()), 1))
    if detail:
        # per-window attempt cost and per-fill net, with trigger times (hour bootstrap / hour bands)
        wcost = np.zeros(len(idx)); wcost[ar] = k * slots * C["att"]
        wnet = -wcost.copy()
        if nf:
            wnet[acc] += pn[acc] - C["fill"] + C["att"]          # the filled attempt is not a failed attempt
        out["w_t"] = D["w_t"][idx]; out["w_net"] = wnet; out["armed_mask"] = armed; out["acc"] = acc; out["idx"] = idx
        out["acc_net"] = per; out["acc_gross"] = pn[acc]; out["acc_fr"] = fr[acc]; out["acc_hold"] = off[acc]; out["acc_size"] = size
        out["arm_a0"] = a0; out["arm_a1"] = a1; out["acc_t"] = D["w_t"][idx[acc]] if nf else np.zeros(0)
    return out

def hourly(o, day):
    """net SOL per clock hour of the day's window (from detail=True)"""
    a, b = V.WIN[day]; t0 = V.pk(a); nh = int(np.ceil((V.pk(b) - t0) / 3600))
    h = np.clip(((o["w_t"] - t0) // 3600).astype(int), 0, nh - 1)
    return np.bincount(h, weights=o["w_net"], minlength=nh)

def fmt(o, h):
    return (f"{o['pnl']:+7.3f} SOL ({o['pnl'] / h * 24:+6.2f}/24h) fills {o['fill']:5d} (skip {o['skip']}) of {o['armed']:6d} armed ({100 * o['fill_rate']:4.1f}%) "
            f"gross {o['gross_per_fill']:+.4f}/fill net {o['per_fill']:+.4f}/fill win {100 * o['winr']:3.0f}% att/fill {o['att_per_fill']:6.0f} "
            f"cost att {o['cost_att']:.3f} fill {o['cost_fill']:.3f}")
