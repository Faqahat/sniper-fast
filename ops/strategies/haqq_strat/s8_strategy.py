#!/usr/bin/env python3
"""HAQQ_STRAT step 8 (read-only, offline): design + replay of a haqq-inspired dip strategy for OUR engine on the dump universe (s7).
Splits by block time: TRAIN = tape start (10-23 19:26) -> 10-25 23:15 PKT, VAL = 10-25 23:15 -> 10-26 23:15, TEST = the last 24 h
(10-26 23:15 -> 10-27 23:15). Models are fit on TRAIN; thresholds, exit and guard are chosen on VAL ('real' landing, our costs);
TEST is read once per frozen config.
Selections:
  ALL      every candidate dump (no model)
  RULE     haqq's profitable cells as a fixed rule (age 5 s - 5 min, curve 35-45 or >= 60 SOL, sell >= 1 SOL)
  IMIT     GBDT P(haqq buys within 2 slots), causal features
  VALUE    GBDT regression of OUR 'real'-landing P&L for the chosen exit
  ORACLE   haqq's actual picks (hindsight upper bound for imitation)
Costs per landed buy / sell / failed (guard) attempt, SOL: NOW 0.00151 / 0.00160 / 0.00051 (our nonce fan-out, H2H.md + window);
  CHEAP 0.00033 / 0.00033 / 0.00004 (haqq's measured). 'calibrated' = real - 0.0022 SOL per fill (MEASURED gap on our 125 live regular fills, s9);
  'cal5' = real - 0.005 (VM1-era gap; conservative).
Concurrency: chronological greedy, one position per mint, at most K open (K = 1 today)."""
import sys, json, pickle, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_strat")
import dd_gbdt as G
from hs_lib import pkt, W0, W1, D
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
COST = {"NOW": (0.00151, 0.00160, 0.00051), "CHEAP": (0.00033, 0.00033, 0.00004)}
CAL = 0.0022          # MEASURED on our 125 real regular fills (s9_calib.py); CAL5 = conservative
CAL5 = 0.005


def main():
    Z = np.load(f"{D}/uni.npz"); X = Z["X"].astype(np.float64); O = Z["O"].astype(np.float64); M = Z["M"]; F = list(Z["feats"])
    LS = list(Z["LS"]); HS = list(Z["HS"]); TPSL = [tuple(x) for x in Z["TPSL"]]
    bt = M["bt"].astype(np.int64)
    tr = bt < W0 - 86400; va = (bt >= W0 - 86400) & (bt < W0); te = (bt >= W0) & (bt < W1)
    P(f"# Strategy replay: universe {len(M):,} dumps; train {tr.sum():,} / val {va.sum():,} / test {te.sum():,}; haqq share {100 * M['hq'][te].mean():.1f}% (test)")
    ndays_tr = (W0 - 86400 - bt[tr].min()) / 86400
    EX = [(f"timer {h}", 2 + 2 * i, 3 + 2 * i) for i, h in enumerate(HS)] + [(f"TP{int(a * 100)}/SL{int(b * 100)}/cap{int(c)}", 2 + 2 * len(HS) + k, None) for k, (a, b, c) in enumerate(TPSL)]
    li = {n: i for i, n in enumerate(LS)}

    def hold_slots(exn):
        if exn.startswith("timer"): return int(exn.split()[1])
        return int(exn.split("cap")[1])

    def pnl(mask, land, ex, guard, cost="NOW", f20=False, K=None, cal=0.0):
        """per-candidate P&L array over the mask (NaN = no trade), after costs; greedy concurrency if K"""
        o = O[:, li[land], :]
        col = ex[2] if (f20 and ex[2] is not None) else ex[1]
        v = o[:, col]; pr = o[:, 0]
        ok = mask & np.isfinite(v) & np.isfinite(pr)
        fill = ok & (pr <= guard)
        cb, cs, cf = COST[cost]
        r = np.full(len(v), np.nan)
        r[fill] = v[fill] - cb - cs - cal
        r[ok & ~fill] = -cf
        if K is not None:
            idx = np.flatnonzero(ok); idx = idx[np.argsort(M["cc"][idx])]
            hs = hold_slots(ex[0]) * 212.0 + 300.0
            open_ = []; busy = {}
            keep = np.zeros(len(v), bool)
            for i in idx:
                t = M["cc"][i]; open_ = [x for x in open_ if x > t]
                m = int(M["mint"][i])
                if len(open_) >= K or busy.get(m, -1) > t: continue
                keep[i] = True
                if fill[i]: open_.append(t + hs); busy[m] = t + hs
            r[~keep] = np.nan
        return r

    def summ(r, days=1.0):
        v = r[np.isfinite(r)]
        return v.sum() / days, len(v) / days

    def boot(r, n=1500):
        v = r[np.isfinite(r)]
        if not len(v): return 0, 0
        g = np.random.default_rng(3); s = [v[g.integers(0, len(v), len(v))].sum() for _ in range(n)]
        return np.percentile(s, 5), np.percentile(s, 95)
    # ---------------- models (fit on TRAIN, early stop on the last 20% of TRAIN by time)
    E = G.edges_of(X, np.flatnonzero(tr)); B = G.binize(X, E)
    tri = np.flatnonzero(tr); tri = tri[np.argsort(bt[tri])]; cut = int(0.8 * len(tri))
    Mi = G.fit(B, M["hq"].astype(float), tri[:cut], tri[cut:], loss="logloss", rounds=800, lr=0.05, depth=5, min_n=200, lam=5.0, sub=0.8, fsub=0.8, seed=1, patience=80)
    s_im = G.predict(Mi, B)
    from math import isnan
    def auc(s, y):
        o = np.argsort(s); y = y[o]; n1 = y.sum(); n0 = len(y) - n1
        return (np.cumsum(~y)[y].sum()) / max(n1 * n0, 1)
    P(f"IMIT model: test AUC {auc(s_im[te], M['hq'][te]):.3f}, val AUC {auc(s_im[va], M['hq'][va]):.3f}")
    imp = G.importance(Mi, X.shape[1]); P("IMIT top features: " + ", ".join(f"{F[j]}" for j in np.argsort(-imp)[:8]))
    # VALUE model per exit candidate (a few exits to keep it quick)
    s_val = {}
    for exn in ("timer 5", "timer 8", "TP10/SL10/cap8", "timer 12"):
        ex = next(e for e in EX if e[0] == exn)
        y = O[:, li["real"], ex[1]].copy(); pr = O[:, li["real"], 0]
        y = np.where(np.isfinite(y) & np.isfinite(pr) & (pr <= 1.10), y, np.nan)
        ok = np.isfinite(y)
        f_ = tri[:cut][ok[tri[:cut]]]; v_ = tri[cut:][ok[tri[cut:]]]
        yy = np.clip(np.nan_to_num(y), -0.2, 0.2)
        Mv = G.fit(B, yy, f_, v_, loss="l2", rounds=600, lr=0.05, depth=4, min_n=300, lam=10.0, sub=0.8, fsub=0.8, seed=2, patience=60)
        s_val[exn] = G.predict(Mv, B)
    age = X[:, F.index("age_s")]; vp = X[:, F.index("vpost")]; sso = X[:, F.index("sell_sol")]
    rule = (age >= 5) & (age <= 300) & (((vp > 35) & (vp <= 45)) | (vp > 60)) & (sso >= 1.0)
    SEL = {"ALL": lambda: np.ones(len(M), bool), "RULE": lambda: rule, "ORACLE haqq picks": lambda: M["hq"]}
    # ---------------- choose config on VAL (real landing, NOW costs, K = None)
    guards = (1.05, 1.10, 1.20, 9.0)
    best = {}
    for nm in ("ALL", "RULE", "ORACLE haqq picks"):
        m = SEL[nm]()
        cands = []
        for ex in EX:
            for g in guards:
                r = pnl(m & va, "real", ex, g); cands.append((summ(r)[0], ex, g, None))
        best[nm] = max(cands, key=lambda x: x[0])
    for nm, sc in (("IMIT", s_im),) + tuple((f"VALUE[{k}]", v) for k, v in s_val.items()):
        cands = []
        qs = np.quantile(sc[va], (0.5, 0.7, 0.8, 0.9, 0.95, 0.97, 0.98, 0.99, 0.995))
        exl = EX if nm == "IMIT" else [next(e for e in EX if e[0] == nm[6:-1])]
        for th in qs:
            for ex in exl:
                for g in guards:
                    r = pnl((sc >= th) & va, "real", ex, g); cands.append((summ(r)[0], ex, g, th))
        best[nm] = max(cands, key=lambda x: x[0])
    P("\n## Configs chosen on VAL (10-25 23:15 -> 10-26 23:15; real landing, our costs today, no position cap)")
    P("| selection | exit | guard | threshold | VAL SOL/day | VAL trades/day |"); P("|---|---|---|---|---|---|")
    for nm, (v, ex, g, th) in best.items():
        msk = (SEL[nm]() if nm in SEL else (s_im if nm == "IMIT" else s_val[nm[6:-1]]) >= th) & va
        P(f"| {nm} | {ex[0]} | {g if g < 9 else 'none'} | {'' if th is None else f'{th:.4f}'} | {v:+.2f} | {summ(pnl(msk, 'real', ex, g))[1]:.0f} |")
    # ---------------- TEST
    P("\n## TEST = last 24 h (10-26 23:15 -> 10-27 23:15 PKT), frozen configs; SOL/day (trades/day). MEASURED replay, INFERRED as a forecast.")
    P("| selection | ideal | 30 ms | 50 ms | 75 ms | 100 ms | real (ours) | real, 5-95% | calibrated | cal5 | 20% fewer followers | real, CHEAP costs | real, K=1 | real, K=3 | real CHEAP K=8 | calibrated CHEAP K=3 |")
    P("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    J = {}
    for nm, (v, ex, g, th) in best.items():
        m = (SEL[nm]() if nm in SEL else (s_im if nm == "IMIT" else s_val[nm[6:-1]]) >= th) & te
        cells = []
        for land in ("ideal", "l30", "l50", "l75", "l100", "real"):
            a, n = summ(pnl(m, land, ex, g)); cells.append(f"{a:+.2f} ({n:.0f})")
        rr = pnl(m, "real", ex, g); lo, hi = boot(rr)
        cal = summ(pnl(m, "real", ex, g, cal=CAL))[0]; cal5 = summ(pnl(m, "real", ex, g, cal=CAL5))[0]
        ck3 = summ(pnl(m, "real", ex, g, cost="CHEAP", K=3, cal=CAL))
        f20 = summ(pnl(m, "real", ex, g, f20=True))[0] if ex[2] is not None else float("nan")
        if ex[2] is not None:
            for fr in (0.05, 0.10):
                o_ = O[:, li["real"], :]; v_ = o_[:, ex[1]] - fr / 0.2 * (o_[:, ex[1]] - o_[:, ex[2]])
                pr_ = o_[:, 0]; ok_ = m & np.isfinite(v_) & np.isfinite(pr_); fl_ = ok_ & (pr_ <= g)
                tot_ = (v_[fl_] - sum(COST["NOW"][:2]) - CAL).sum() - COST["NOW"][2] * (ok_ & ~fl_).sum()
                P(f"    {nm}: {int(fr * 100)}% fewer followers, calibrated, our costs: {tot_:+.2f} SOL/day")
        ch = summ(pnl(m, "real", ex, g, cost="CHEAP"))[0]
        k1 = summ(pnl(m, "real", ex, g, K=1)); k3 = summ(pnl(m, "real", ex, g, K=3)); k8 = summ(pnl(m, "real", ex, g, cost="CHEAP", K=8))
        P(f"| {nm} ({ex[0]}, g {g if g < 9 else 'none'}) | " + " | ".join(cells) + f" | {lo:+.1f}..{hi:+.1f} | {cal:+.2f} | {cal5:+.2f} | {f20:+.2f} | {ch:+.2f} | {k1[0]:+.2f} ({k1[1]:.0f}) | {k3[0]:+.2f} ({k3[1]:.0f}) | {k8[0]:+.2f} ({k8[1]:.0f}) | {ck3[0]:+.2f} ({ck3[1]:.0f}) |")
        J[nm] = dict(exit=ex[0], guard=g, th=th, real=summ(rr)[0], lo=lo, hi=hi, cal=cal, cal5=cal5, cheap_k3_cal=ck3[0], f20=f20, cheap=ch, k1=k1[0], k3=k3[0], k8cheap=k8[0])
    # exit / guard sweep on test for IMIT picks (information only, not used for choice)
    v, ex0, g0, th0 = best["IMIT"]; m = (s_im >= th0) & te
    P(f"\nIMIT picks on TEST, exit x guard sweep at real landing, our costs (information only; config was frozen on VAL: {ex0[0]}, guard {g0}):")
    P("| exit | g 1.05 | g 1.10 | g 1.20 | none |"); P("|---|---|---|---|---|")
    for ex in EX:
        P(f"| {ex[0]} | " + " | ".join(f"{summ(pnl(m, 'real', ex, g))[0]:+.2f}" for g in guards) + " |")
    # fill rate and entry price ratio vs haqq's picks
    o = O[:, li["real"], 0]
    P(f"\nEntry price / post-dump price at our real landing: haqq picks p50 {np.nanmedian(o[te & M['hq']]):.3f} (fill at 1.05: {100 * np.nanmean(o[te & M['hq']] <= 1.05):.0f}%), "
      f"other dumps p50 {np.nanmedian(o[te & ~M['hq']]):.3f} (fill {100 * np.nanmean(o[te & ~M['hq']] <= 1.05):.0f}%)")
    json.dump(J, open(f"{D}/s8.json", "w"), indent=1, default=float)
    pickle.dump(dict(s_im=s_im, best={k: (v[0], v[1][0], v[2], v[3]) for k, v in best.items()}), open(f"{D}/s8_scores.pkl", "wb"))
    open(f"{D}/s8.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
