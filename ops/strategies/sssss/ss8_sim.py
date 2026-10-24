#!/usr/bin/env python3
# Shared replay helpers for the sssssDdM replica (read-only). Our buy lands `lat` ms after a trigger trade (modelled
# arrival), +5% guard vs the price right after the trigger (else failed buy -0.0005 SOL), follower buys whose slippage limit
# our buy breaks are dropped (p1_build slack model), sells applied as tokens in, graduation -> exit at pre-graduation state.
# EXIT DSL: {"any_of": [[[feat, op, val], ...], ...], "max_slots": int|null, "tp": mult|null, "sl": mult|null}
#   evaluated at every later trade (not ours; sssssDdM's own trades are removed when `skip_uid` is given): position features
#   ev (1 buy / 0 sell), sol, move, wt, mult, peak, dd, held, sold_since, bought_since, net_since, n_sells_3, n_buys_3,
#   sell_sol_3, buy_sol_3, net_3, n_sells_10, n_buys_10, sell_sol_10, buy_sol_10, net_10, ret3, ret10, sib_sold.
#   When it fires at a trade in slot S, our sell fills after all trades of slot S (end-of-slot fill, ~35 ms reaction).
# Costs: pump fee (event bps) both sides + FIX SOL per round trip.
import numpy as np, zlib
SMS = 212.0; GUARD = 1.05; GRADV = 113e9; FAIL = 0.0005
WDK = zlib.crc32(b"ssssswdk4RR8HqkE3uwUWzDbd6mXFTTPjcXBKNzQ57E")
OPS = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b, ">": lambda a, b: a > b, "<": lambda a, b: a < b, "==": lambda a, b: a == b, "!=": lambda a, b: a != b,
       "in": lambda a, b: a in b, "not_in": lambda a, b: a not in b}
WTC = {"creator": 1, "insider": 2, "new": 3, "fresh": 3, "bot": 4, "other": 0, **{f"F{k}": 10 + k for k in range(1, 11)}}
WIN = {"n_sells_3": "ns3", "n_buys_3": "nb3", "sell_sol_3": "ssol3", "buy_sol_3": "bsol3", "net_3": "net3", "n_sells_10": "ns10", "n_buys_10": "nb10",
       "sell_sol_10": "ssol10", "buy_sol_10": "bsol10", "net_10": "net10", "ret3": "ret3", "ret10": "ret10", "ret1": "ret1", "ns1": "ns1", "nb1": "nb1",
       "ssol1": "ssol1", "bsol1": "bsol1", "dd3": "dd3"}
POSF = {"ev", "sol", "move", "wt", "mult", "peak", "dd", "held", "sold_since", "bought_since", "net_since", "sib_sold"}

def norm_exit(x):
    """validate / normalize an exit rule dict -> (conds, max_slots, tp, sl) or raise ValueError"""
    conds = []
    for lst in x.get("any_of") or []:
        cl = []
        for c in lst:
            if not isinstance(c, (list, tuple)) or len(c) != 3: raise ValueError(f"cond {c}")
            f, op, v = c
            if op not in OPS: raise ValueError(f"op {op}")
            if f == "ev": v = {"buy": 1, "sell": 0}.get(v, v) if not isinstance(v, list) else [{"buy": 1, "sell": 0}.get(z, z) for z in v]
            if f == "wt": v = WTC.get(v, v) if not isinstance(v, list) else [WTC.get(z, z) for z in v]
            if f not in POSF and f not in WIN: raise ValueError(f"feature {f}")
            if op in ("in", "not_in") and not isinstance(v, list): v = [v]
            if op not in ("in", "not_in"): v = float(v)
            cl.append((f, op, v))
        if cl: conds.append(cl)
    ms = x.get("max_slots"); ms = int(ms) if isinstance(ms, (int, float)) and ms > 0 else 3000
    tp = x.get("tp"); sl = x.get("sl")
    tp = float(tp) if isinstance(tp, (int, float)) and tp > 1 else None
    sl = float(sl) if isinstance(sl, (int, float)) and 0 < sl < 1 else None
    return conds, min(ms, 6000), tp, sl

def sib_last_sell(d):
    """per trade: slot of the most recent sibling (ssssswdk) sell in this token up to and including this trade (-1e9 if none)"""
    n = len(d["s"]); out = np.full(n, -10 ** 9, np.int64)
    w = np.flatnonzero((d["uid"] == WDK) & (d["buy"] == 0))
    tok = d["tok"]
    for k in w:
        e = int(d["tend"][k]); hi = min(e, k + 4000)
        seg = slice(k, hi)
        m = (d["s"][seg] <= d["s"][k] + 2)
        out[k:hi][m] = np.maximum(out[k:hi][m], d["s"][k])
    return out

def enter(d, k, lat, size, fix):
    """our buy after trigger trade k: returns (state dict) or a failed / None result"""
    end = int(d["tend"][k]); fr = float(d["fr"][k])
    land_arr = float(d["arr"][k]) + lat; j = k + 1
    while j < end and d["arr"][j] < land_arr: j += 1
    Vb = float(d["vsol"][j - 1]); Tb = float(d["vtok"][j - 1])
    if Vb >= GRADV or Tb <= 0: return None
    if (Vb / Tb) / (float(d["vsol"][k]) / float(d["vtok"][k])) > GUARD: return dict(fail=1, pnl=-FAIL, B=size, hold=0, exit_arr=land_arr, why="guard")
    B = size if size > 0 else min(max(-size * Vb / 1e9, 0.35), 0.75)          # size < 0: fraction of curve SOL, capped 0.35-0.75
    X = B * 1e9 / (1 + fr); q = Tb * X / (Vb + X)
    return dict(j=j, V=Vb + X, T=Tb - q, q=q, p_in=X / q, B=B, fr=fr, land_slot=int(land_arr // SMS), land_arr=land_arr, end=end, fail=0)

def walk(d, st, rule, fix, skip_uid=None, sibs=None, FI=None, exit_lat=None):
    conds, ms, tp, sl = rule
    s = d["s"]; V, T, q, p_in, fr = st["V"], st["T"], st["q"], st["p_in"], st["fr"]
    j = st["j"]; end = st["end"]; t_end = st["land_slot"] + ms
    pk = 1.0; ssum = bsum = 0.0; pend = None; exit_slot = None; why = "timer"; pend_arr = None; jf = None
    F = d["F"]; A = d["arr"]
    need_win = any(f in WIN for cl in conds for f, _, _ in cl)
    while j < end:
        st_ = int(s[j])
        if pend_arr is not None and A[j] >= pend_arr: exit_slot = st_; break
        if pend is not None and pend_arr is None and st_ > pend: exit_slot = pend; break
        if st_ > t_end: exit_slot = t_end; why = "timer"; break
        if skip_uid is not None and d["uid"][j] == skip_uid: j += 1; continue
        sol = float(d["sol"][j]); buy = bool(d["buy"][j])
        if buy:
            dt = T * sol / (V + sol)
            if dt < float(d["tokn"][j]) / (1.0 + float(d["slack"][j])): j += 1; continue
            if V + sol >= GRADV: exit_slot = st_; why = "grad"; break
            V += sol; T -= dt; bsum += sol / 1e9
        else:
            tk = float(d["tokn"][j]); so = V * tk / (T + tk); V -= so; T += tk; ssum += sol / 1e9
        if pend is None:
            m = (V / T) / p_in; pk = max(pk, m)
            if tp and m >= tp: pend = st_; why = "tp"
            elif sl and m <= sl: pend = st_; why = "sl"
            if pend is not None and jf is None: jf = j
            if pend is not None and exit_lat is not None and pend_arr is None: pend_arr = float(A[j]) + exit_lat
            elif conds:
                feat = None
                for ci, cl in enumerate(conds):
                    ok = True
                    for f, op, v in cl:
                        if f == "ev": x = 1 if buy else 0
                        elif f == "sol": x = sol / 1e9
                        elif f == "move": x = float(F[j, FI["move"]])
                        elif f == "wt": x = int(d["wt"][j])
                        elif f == "mult": x = m
                        elif f == "peak": x = pk
                        elif f == "dd": x = 1 - m / pk
                        elif f == "held": x = st_ - st["land_slot"]
                        elif f == "sold_since": x = ssum
                        elif f == "bought_since": x = bsum
                        elif f == "net_since": x = bsum - ssum
                        elif f == "sib_sold": x = 1 if (sibs is not None and st_ - sibs[j] <= 2) else 0
                        else: x = float(F[j, FI[WIN[f]]])
                        if not OPS[op](x, v): ok = False; break
                    if ok:
                        pend = st_; why = f"rule{ci}"; jf = j
                        if exit_lat is not None: pend_arr = float(A[j]) + exit_lat
                        break
        j += 1
    if exit_slot is None: exit_slot = pend if pend is not None else min(t_end, int(s[end - 1]))
    got = V * q / (T + q) * (1 - fr) / 1e9
    return dict(fail=0, pnl=got - st["B"] - fix, B=st["B"], hold=exit_slot - st["land_slot"], exit_arr=(exit_slot + 1) * SMS, why=why, jf=jf)

def run_entries(d, ks, lat, size, rule, fix, one_at_a_time=True, skip_uid=None, sibs=None, max_n=None, exit_lat=None):
    """ks = trigger indices (any order). one_at_a_time: greedy in landing order, skip while a position is open."""
    FI = d["FI"]; order = ks[np.argsort(d["arr"][ks], kind="stable")]
    busy = -1.0; out = []
    for k in order:
        k = int(k)
        if one_at_a_time and d["arr"][k] + lat < busy: continue
        st = enter(d, k, lat, size, fix)
        if st is None: continue
        if st.get("fail"): st["k"] = k; out.append(st); continue
        r = walk(d, st, rule, fix, skip_uid, sibs, FI, exit_lat); r["k"] = k; out.append(r)
        if one_at_a_time: busy = r["exit_arr"]
        if max_n and len(out) >= max_n: break
    return out

def stats(rs):
    if not rs: return dict(n=0)
    p = np.array([r["pnl"] for r in rs]); ok = [r for r in rs if not r["fail"]]
    B = sum(r["B"] for r in ok) or 1e-9; srt = np.sort(p)
    return dict(n=len(rs), fail=len(rs) - len(ok), pnl=round(float(p.sum()), 2), mean=round(float(p.mean()), 4), per_sol=round(float(p.sum() / B), 4),
                win=round(float((p > 0).mean()), 3), wo_top1=round(float(srt[:-max(1, len(p) // 100)].sum()), 2),
                hold_med=float(np.median([r["hold"] for r in ok])) if ok else 0)
