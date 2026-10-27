#!/usr/bin/env python3
# Engine replay + costs for the pre-sent conditional-buy windows (ps4_<day>.npz). Read-only.
# Per config: windows of one family passing a filter -> one armed window per token at a time (a fill blocks the token until our
# sell) -> 2 servers, one open position each (a pre-sent order needs no near leader, so any free server takes a fill; while BOTH
# are busy nothing is sent and nothing fills) -> costs:
#   every attempt that does not fill: base 5,000 lamports + priority (CU limit x price)   [k attempts per armed slot, counted
#   for every armed slot of every window, filled or not]
#   a fill: tip 0.001 SOL + base + priority;  the sell: one more tx (base + priority) (+ optional sell tip)
import json, time, bisect
import numpy as np
import ps_common as C
SMS = 212.0; MARGIN = 300.0
M = json.load(open(f"{C.OUT}/ps4_meta.json"))
EXN = M["exits"]; EXI = {k: i for i, k in enumerate(EXN)}; YS = M["ys"]; DMOD = M["dmod"]; SIZES = M["sizes"]
FI = {k: i for i, k in enumerate(M["feats"])}
FEE = {"cheap": (5000 + 60_000 * 1_000 / 1e6) / 1e9, "now": (5000 + 100_000 * 5_000_000 / 1e6) / 1e9}
TIP = 0.001
KDEF = {"a": 20, "b": 20, "c": 20, "r1": 1, "r4": 4, "r20": 20}     # attempts per armed slot consistent with each queue model

def hours(day):
    a, b = C.WIN[day]; return (C.pk(b) - C.pk(a)) / 3600.0

def load(day):
    z = np.load(f"{C.OUT}/ps4_{day}.npz"); D = {k: z[k] for k in z.files}
    tp = C.load(day, cols=("s", "arr", "bt", "tok"))
    D["day"] = day; D["arr"] = tp["arr"]; D["s_tape"] = tp["s"]; D["t_tape"] = tp["t"]
    D["w_t"] = tp["t"][D["w_j"]]
    D["w_in"] = C.in_win(dict(day=day), D["w_t"])
    D["f_time"] = tp["arr"][D["f_x"]] + D["f_D"]
    nW = len(D["w_fam"]); D["nW"] = nW
    # fill row per (y, d) per window (-1 = none)
    FR = np.full((len(YS), len(DMOD), nW), -1, np.int64)
    FR[D["f_y"], D["f_d"], D["f_w"]] = np.arange(len(D["f_w"]))
    D["FR"] = FR
    D["hours"] = hours(day)
    return D

def wfeat(D, k): return D["w_f"][:, FI[k]]

def run(D, wmask, W, y, dm, size, ex, k=None, fee="cheap", sell_tip=0.0, end_cre=False, servers=2, detail=False, busy_pause=True):
    """returns dict with pnl (net SOL), fills, windows armed, attempts, costs, per-fill, etc."""
    yi = YS.index(y); di = DMOD.index(dm); si = SIZES.index(size); e = EXI[ex] if isinstance(ex, str) else ex
    k = KDEF[dm] if k is None else k; fa = FEE[fee] if isinstance(fee, str) else fee
    idx = np.flatnonzero(wmask & D["w_in"])
    if len(idx) == 0: return dict(pnl=0.0, fill=0, armed=0, att=0, gross=0.0, cost_att=0.0, cost_fill=0.0, per_fill=0.0, winr=0.0, skip=0, rows=[])
    st = D["w_start"][idx]; en = np.minimum(D["w_end"][idx], st + W * SMS)
    if end_cre:
        cs = D["w_f"][idx, FI["cre_sell_ms"]].astype(np.float64)
        en = np.minimum(en, st + cs + 30.0)
    fr = D["FR"][yi, di, idx]
    has = fr >= 0
    ft = np.where(has, D["f_time"][np.maximum(fr, 0)], np.inf)
    valid = has & (ft < en)
    pid = np.where(valid, D["f_pid"][np.maximum(fr, 0)], -1)
    sin = np.where(valid, D["p_sin"][np.maximum(pid, 0)], 0)
    off = np.where(valid, D["p_off"][np.maximum(pid, 0), si, e], 0).astype(np.int64)
    pn = np.where(valid, D["p_pnl"][np.maximum(pid, 0), si, e], 0.0)
    xt = (sin + off) * SMS + 75.0                                   # our sell lands
    tok = D["w_tok"][idx]
    # one armed window per token at a time; a fill blocks the token until our sell
    o = np.lexsort((st, tok)); armed = np.zeros(len(idx), bool); aend = np.zeros(len(idx))
    last_tok = -1; free_at = -np.inf
    for r in o.tolist():
        t = tok[r]
        if t != last_tok: last_tok = t; free_at = -np.inf
        if st[r] < free_at: continue
        armed[r] = True
        if valid[r]: aend[r] = ft[r]; free_at = xt[r] + MARGIN
        else: aend[r] = en[r]; free_at = en[r]
    # engine: fills in time order, any free server
    fills = np.flatnonzero(armed & valid); fills = fills[np.argsort(ft[fills], kind="stable")]
    busy = [-np.inf] * servers; acc = []; skip = 0; ivs = []
    for r in fills.tolist():
        t0 = ft[r]
        sv = min(range(servers), key=lambda s_: busy[s_])
        if busy[sv] > t0: skip += 1; continue
        busy[sv] = xt[r] + MARGIN; acc.append(r); ivs.append((sv, t0, busy[sv]))
    # both-busy intervals (attempts paused, nothing sent)
    bb = []
    if busy_pause and servers == 2 and ivs:
        A_ = sorted((a, b) for s_, a, b in ivs if s_ == 0); B_ = sorted((a, b) for s_, a, b in ivs if s_ == 1)
        i = j = 0
        while i < len(A_) and j < len(B_):
            lo = max(A_[i][0], B_[j][0]); hi = min(A_[i][1], B_[j][1])
            if lo < hi: bb.append((lo, hi))
            if A_[i][1] < B_[j][1]: i += 1
            else: j += 1
    bbs = np.array([x[0] for x in bb]); bbe = np.array([x[1] for x in bb])
    ar = np.flatnonzero(armed)
    dur = np.maximum(aend[ar] - st[ar], 0.0)
    if len(bb):
        # subtract overlap with both-busy intervals
        cum = np.concatenate([[0.0], np.cumsum(bbe - bbs)])
        def ov(a, b):
            i0 = bisect.bisect_right(bbe, a); i1 = bisect.bisect_left(bbs, b)
            if i1 <= i0: return 0.0
            tot = cum[i1] - cum[i0]
            tot -= max(0.0, a - bbs[i0]) if i0 < len(bbs) else 0.0
            tot -= max(0.0, bbe[i1 - 1] - b) if i1 - 1 >= 0 else 0.0
            return max(tot, 0.0)
        dur = np.array([max(dd - ov(st[r], aend[r]), 0.0) for dd, r in zip(dur.tolist(), ar.tolist())])
    slots = np.maximum(np.ceil(dur / SMS), 1.0)
    att = float(k * slots.sum())
    acc = np.array(acc, np.int64)
    nf = len(acc)
    gross = float(pn[acc].sum()) if nf else 0.0
    cost_fill = nf * (TIP + fa + fa + sell_tip)
    cost_att = (att - nf) * fa
    pnl = gross - cost_fill - cost_att
    per = (pn[acc] - (TIP + 2 * fa + sell_tip)) if nf else np.zeros(0)
    out = dict(pnl=pnl, fill=nf, armed=int(armed.sum()), att=att, gross=gross, cost_att=cost_att, cost_fill=cost_fill,
               per_fill=pnl / nf if nf else 0.0, gross_per_fill=gross / nf if nf else 0.0, winr=float((per > 0).mean()) if nf else 0.0, skip=skip,
               att_per_fill=att / nf if nf else float("inf"), armed_slots=float(slots.sum()), k=k)
    if detail:
        out["acc_rows"] = idx[acc]                       # window ids of accepted fills
        out["acc_fr"] = fr[acc]; out["acc_pnl"] = per; out["acc_t"] = D["w_t"][idx[acc]]
        out["acc_x"] = D["f_x"][fr[acc]]; out["acc_pmin"] = D["p_min"][pid[acc]]
        out["acc_tok"] = tok[acc]; out["acc_ft"] = ft[acc]; out["acc_xt"] = xt[acc]
        out["arm_rows"] = idx[ar]; out["arm_slots"] = slots; out["arm_t"] = D["w_t"][idx[ar]]
        cf = fills                                             # armed fills before the engine (for a shared-server replay)
        out["cand_ft"] = ft[cf]; out["cand_xt"] = xt[cf]; out["cand_net"] = pn[cf] - (TIP + 2 * fa + sell_tip); out["cand_tok"] = tok[cf]
        out["cand_x"] = D["f_x"][fr[cf]]; out["cand_pid"] = pid[cf]; out["cand_sin"] = sin[cf]; out["cand_cost"] = TIP + 2 * fa + sell_tip
    return out

def fmt(o, h):
    return (f"{o['pnl']:+7.2f} SOL ({o['pnl'] / h * 24:+6.2f}/24h)  fills {o['fill']:5d} (skip {o['skip']}) of {o['armed']:6d} armed  "
            f"gross {o['gross_per_fill']:+.4f}/fill  net {o['per_fill']:+.4f}/fill  win {100 * o['winr']:3.0f}%  att/fill {o['att_per_fill']:7.1f}  "
            f"cost att {o['cost_att']:.2f} fill {o['cost_fill']:.2f}")
