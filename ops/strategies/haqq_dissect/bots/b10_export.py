#!/usr/bin/env python3
"""BOTS step 10 (read-only): export EVERY decision of the walk-forward 'our 247/248' rule (b6 picks, all test days, all mints) for a hand
audit against the chain. One JSON line per decision: buy (the decision, at the trigger dump), fill / fail (where the buy lands = right
after the trade 'after_slot/after_idx', rank-model draw 0), sell (modelled decision time and landing slot; median MEASURED delay).
P&L: model (draw 0, delay-averaged exact replay, = b5), model mean over the 4 draws, calibrated (a x model + b, per exit/guard, b6).
usage: b10_export.py BOT COST   -> bots/decisions.jsonl"""
import sys, json, pickle, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import xlib as X
from xsim import Pos
from x7_ourexits import delays
from x12_wave import ev
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/bots"
SIZES = (0.30, 0.40); HZ = 55


def trig_time(S, pol, dt):
    """chain-clock ms after our buy at which the sell is decided (mirrors x12.ev / x7 timer)"""
    k = pol[0]
    if S.n == 0: return 0.0, "react"
    if k == "T": return S.slot_start(pol[1]), "timer"
    if k == "MS": return float(pol[1]), "react"
    bt = S.dcc[S.bu]
    if k == "RIDE":
        _, t1, s, t = pol
        rec = bt[(bt <= t1) & (bt > t1 - s)]
        if not len(rec): return float(t1), "react"
        later = bt[bt > t1 - s]; gaps = np.diff(np.concatenate([later, [np.inf]]))
        j = np.argmax(gaps >= s); return float(min(max(later[j] + s, t1), t)), "react"
    raise ValueError(pol)


def main():
    bot, cost = int(sys.argv[1]), sys.argv[2]
    t0 = time.time()
    PK = pickle.load(open(f"{OUT}/b6_picks.pkl", "rb"))
    DR, DT, _ = delays(); dmed_r = float(np.median(DR)); dmed_t = float(np.median(DT["reg"]))
    ids, idm = L.ids_map(); our = [idm[w] for w in L.WAL.values() if w in idm]
    U = np.load(f"{L.D}/uni.npz"); M = U["M"]; RR = U["R"]; names = list(U["names"]); rk = [i for i, n in enumerate(names) if n.startswith("rank")]
    B5 = np.load(f"{OUT}/b5.npz"); PN = B5["PN"]; F5 = B5["F5"]
    Y = np.load(f"{OUT}/b2.npz")
    need = np.unique(np.concatenate([v["idx"] for (b, c, D), v in PK.items() if b == bot and c == cost]))
    mints = np.unique(M["mint"][need])
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    user = np.asarray(T["user"]); keep = ~np.isin(user, our)
    mt = np.asarray(T["mint"])[keep]; o = np.argsort(mt, kind="stable"); gpos = np.flatnonzero(keep)[o]      # u1 order -> original rows
    mts = mt[o]; del mt
    sel = np.isin(mts, mints); rows = gpos[sel]; upos = np.flatnonzero(sel)                                   # u1-order index of each kept row
    A = {c: np.asarray(T[c])[rows] for c in ("slot", "idx", "user", "buy", "sol", "tok", "vsol", "vtok", "fee_bps", "cfee_bps", "bt")}
    u2l = {int(u): i for i, u in enumerate(upos)}                                                              # u1 index -> local
    um, st = np.unique(mts[sel], return_index=True); en = np.append(st[1:], len(rows)); span = {int(m): (int(a), int(b)) for m, a, b in zip(um, st, en)}
    cc_all = L.cc(A["slot"].astype(np.int64), A["idx"].astype(np.int64))
    print(f"tape cut {len(rows):,} rows ({time.time() - t0:.0f}s)", flush=True)
    PLs = [str(x) for x in B5["PL"]]
    out = open(f"{OUT}/decisions.jsonl", "a" if len(sys.argv) > 3 and sys.argv[3] == "append" else "w"); n = 0
    for (b, c, D), v in sorted(PK.items(), key=lambda kv: kv[0][2]):
        if b != bot or c != cost: continue
        pi = v["pi"]; si = v["si"]; size = SIZES[si]; pol = eval(v["exit"]); gi = v["guard"]
        for u, p in sorted(zip(v["idx"].tolist(), v["p"].tolist()), key=lambda x: M["cc"][x[0]]):
            jd = u2l[int(M["row"][u])]; m = int(M["mint"][u]); a, e = span[m]
            sl = A["slot"][a:e].astype(np.int64); ix = A["idx"][a:e].astype(np.int64); bu = A["buy"][a:e].astype(bool)
            so = A["sol"][a:e] / 1e9; tk = A["tok"][a:e].astype(np.float64); vs = A["vsol"][a:e] / 1e9; vt = A["vtok"][a:e].astype(np.float64)
            cc = cc_all[a:e]; jl = jd - a
            fee = (A["fee_bps"][jd] + A["cfee_bps"][jd]) / 1e4 or X.FEE
            g = max(u2l[int(RR[u, rk[0]] - 1)] - a, jl) if int(RR[u, rk[0]] - 1) in u2l else jl
            sn = size / (1 + fee); tokd = vt[jl] - vs[jl] * vt[jl] / (vs[jl] + sn); te = vt[g] - vs[g] * vt[g] / (vs[g] + sn)
            fill = True if gi == "none" else bool(te >= tokd / 1.05)
            mdl0 = float(PN[u, 0, si, 0, pi]) if fill else 0.0
            mmean = float(np.mean([PN[u, d, si, 0, pi] if (gi == "none" or F5[u, d, si]) else 0.0 for d in range(PN.shape[1])]))
            base = dict(day=D, mint=ids[m], dump_slot=int(sl[jl]), dump_idx=int(ix[jl]), dump_seller=ids[int(A["user"][jd])], dump_sol=round(float(so[jl]), 4),
                        dump_drop_pct=round(100 * float(1 - (vs[jl] / vt[jl]) / (vs[jl - 1] / vt[jl - 1])) if jl > 0 else 0.0, 2), score=round(float(p), 4),
                        bot_like=bot, his_buy=bool(Y[f"Y{bot}"][u]))
            out.write(json.dumps(dict(kind="buy", decision_after_slot=int(sl[jl]), decision_after_idx=int(ix[jl]), decision_cc_ms=round(float(cc[jl]), 1), size_sol=size,
                                      guard=gi, exit=v["exit"], min_tokens_out=(None if gi == "none" else int(tokd / 1.05)), **base)) + "\n")
            kind = "fill" if fill else "fail"
            rec = dict(kind=kind, land_after_slot=int(sl[g]), land_after_idx=int(ix[g]), k_ahead=int(g - jl), price_sol_per_token=float(vs[g] / vt[g]),
                       price_vs_post_dump=round(float(tokd / max(te, 1)), 4), tokens=int(te), sol_in=size, **base)
            out.write(json.dumps(rec) + "\n"); n += 2
            if not fill: continue
            hi = int(np.searchsorted(sl, sl[g] + HZ, side="right")); js = np.arange(g + 1, hi); c0 = cc[g] + 0.01
            pp = dict(kind="reg", V0=float(vs[g]), T0=float(vt[g]), sin=float(sn), cost=size, fee=float(fee), off_in_slot=float(c0 - sl[g] * X.SMS),
                      dcc=(cc[js] - c0).astype(np.float64), bu=bu[js].copy(), so=so[js].copy(), tk=tk[js].copy())
            S = Pos(pp, 1.0); tt, kd = trig_time(S, pol, DT["reg"])
            land = c0 + tt + (dmed_t if kd == "timer" else dmed_r)
            q = int(np.searchsorted(cc, land, side="right")) - 1
            val = float(S.val_q(np.array(S.q_at(land - c0)))) if S.n else S.v_pre
            out.write(json.dumps(dict(kind="sell", decide_cc_ms=round(float(c0 + tt), 1), land_after_slot=int(sl[max(q, g)]), land_after_idx=int(ix[max(q, g)]),
                                      sol_out_at_median_delay=round(val * size, 6), pnl_model_draw0=round(mdl0, 6), pnl_model_mean4=round(mmean, 6),
                                      pnl_calibrated=round(v["a"] * mmean + v["b"], 6), exit=v["exit"], **base)) + "\n"); n += 1
    out.close()
    print(f"{n:,} decisions -> decisions.jsonl ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
