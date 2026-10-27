#!/usr/bin/env python3
"""DV8 step 3b/4 (read-only, offline): walk-forward DV8 gate + replay on every usable test day, with OUR landing model.
Days = 24 h windows ending 23:15 PKT (dv8lib.day_of); candidates only from usable hours (c0: slot coverage >= 95% and trades >= 50%
of the median hour). Test day D: gate trained on days < D-1 (GBDT, dd_gbdt, early stop on the last 20% of train by time),
config (exit H, score threshold) chosen on day D-1 ONLY, then day D read once.
Gate target (per exit H) = expected curve P&L per attempt at our landing = mean over the rank-model draws of fill x exact P&L.
Replay of the picks (per rank draw, then averaged): chronological greedy, at most K open, one per mint, a filled position is busy for
H slots x 212 ms + 300 ms; unfilled attempts cost the failed-buy cost and do not occupy.
P&L rows: ideal (land right after the dump), ours (rank landing, exact followers, uncalibrated), calibrated = a x curve P&L + b per
fire (OLS of live vs modelled on our 1,544 live fires out-of-sample by server, c2), conservative = 5% quantile over a 2,000-sample
bootstrap of (a, b); minus tx costs.
Costs per landed buy / sell / failed buy, SOL: NOW 0.00175 / 0.00177 / 0.00053 (MEASURED, l2), CHEAP 0.00033 / 0.00033 / 0.00004
(haqq's recipe, haqq_strat s3).
Out: dv8/g1.txt, dv8/g1.json, dv8/g1_picks.pkl"""
import json, pickle, heapq, sys, collections, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect")
import dd_gbdt as G
import dv8lib as L
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); out.append(s)
COST = {"NOW": (0.00175, 0.00177, 0.00053), "CHEAP": (0.00033, 0.00033, 0.00004)}
QS = (0.5, 0.7, 0.8, 0.85, 0.9, 0.93, 0.95, 0.97, 0.98, 0.99, 0.995)
EXITS = (0, 1, 2)          # HS index: 5, 8, 12 (30 kept for the 'buy every dump' check)


def load(keep_mayhem=False):
    """mayhem tokens (create flag) are excluded unless keep_mayhem: their TradeEvent reserves are not a constant-product curve
    (the s7 vshift replay turns them into fake +50 mSOL/fill profits, g2)"""
    Z = np.load(f"{L.D}/uni.npz")
    d = {k: Z[k] for k in Z.files}
    hrs = json.load(open(f"{L.D}/hours.json"))
    good = {r["h"] for r in hrs["rows"] if r["usable"]}
    bt = d["M"]["bt"].astype(np.int64)
    hstart = (bt + 18000) // 3600 * 3600 - 18000
    d["usable"] = np.isin(hstart, list(good))
    d["mayhem"] = np.load(f"{L.D}/mayhem.npy")
    if not keep_mayhem: d["usable"] &= ~d["mayhem"]
    d["day"] = ((bt - L.DAY0) // 86400).astype(int)
    d["uh"] = collections.Counter(int((r["h"] + 1800 - L.DAY0) // 86400) for r in hrs["rows"] if r["usable"])
    return d


def calib_boot():
    pf = pickle.load(open(f"{L.D}/c2_perfire.pkl", "rb"))
    x = np.array([p["rank_oos"] for p in pf]); y = np.array([p["live"] for p in pf])
    A = np.vstack([x, np.ones(len(x))]).T
    a, b = np.linalg.lstsq(A, y, rcond=None)[0]
    g = np.random.default_rng(9); bs = []
    for _ in range(2000):
        ii = g.integers(0, len(x), len(x)); bs.append(np.linalg.lstsq(A[ii], y[ii], rcond=None)[0])
    return (a, b), np.array(bs)


class Rep:
    def __init__(s, d):
        s.d = d; s.M = d["M"]; s.FILL = d["FILL"]; s.PN = d["PN"]; s.HS = list(d["HS"]); s.names = list(d["names"])
        s.ranks = [i for i, n in enumerate(s.names) if n.startswith("rank")]
        s.near = d["near"]; s.cc = s.M["cc"]; s.mint = s.M["mint"].astype(np.int64)

    def run(s, mask, hi, K=3, model="rank", fol=0, near_only=False, keep=None):
        """returns per-draw arrays (fires, fills, wins, sumPN(curve, fills), list of picked idx) averaged later"""
        m = mask & np.isfinite(s.PN[:, 0, hi, 0])
        if near_only: m &= s.near
        idx = np.flatnonzero(m); idx = idx[np.argsort(s.cc[idx])]
        cols = s.ranks if model == "rank" else [s.names.index(model)]
        hold = s.HS[hi] * 212.0 + 300.0
        res = []
        for c in cols:
            fill = s.FILL[idx, c]; pn = s.PN[idx, c, hi, fol]
            ok = fill & np.isfinite(pn)
            if K is None:
                take = np.ones(len(idx), bool)
            else:
                take = np.zeros(len(idx), bool); heap = []; busy = {}
                for k, i in enumerate(idx):
                    t = s.cc[i]
                    while heap and heap[0] <= t: heapq.heappop(heap)
                    mt = s.mint[i]
                    if len(heap) >= K or busy.get(mt, -1.0) > t: continue
                    take[k] = True
                    if ok[k]: heapq.heappush(heap, t + hold); busy[mt] = t + hold
            res.append(dict(idx=idx[take], fill=ok[take], pn=np.where(ok[take], pn[take], 0.0)))
        return res

    @staticmethod
    def money(res, cost="NOW", a=1.0, b=0.0, calib=False):
        cb, cs, cf = COST[cost]; tot = []
        for r in res:
            nf = r["fill"].sum(); n = len(r["fill"])
            g = (a * r["pn"].sum() + b * n) if calib else r["pn"].sum()
            tot.append(g - nf * (cb + cs) - (n - nf) * cf)
        return float(np.mean(tot))

    @staticmethod
    def counts(res):
        return dict(fires=np.mean([len(r["fill"]) for r in res]), fills=np.mean([r["fill"].sum() for r in res]),
                    wins=np.mean([(r["pn"] > 0).sum() for r in res]))


def main():
    t0 = time.time()
    d = load(); R = Rep(d); M = d["M"]; X = d["X"].astype(np.float64); day = d["day"]; us = d["usable"]
    (A0, B0), BS = calib_boot()
    P(f"# DV8 walk-forward replay; universe {len(M):,} candidates, usable {us.sum():,}; calibration live = {A0:.2f} x modelled {1000 * B0:+.2f} mSOL/fire "
      f"(bootstrap a 5-95% {np.percentile(BS[:, 0], 5):.2f}..{np.percentile(BS[:, 0], 95):.2f}, b {1000 * np.percentile(BS[:, 1], 5):+.2f}..{1000 * np.percentile(BS[:, 1], 95):+.2f})")
    days = sorted(set(day[us].tolist()))
    P("candidates per day (usable hours): " + ", ".join(f"D{k} {int((us & (day == k)).sum()):,} ({d['uh'].get(k, 0)} h)" for k in days))
    # targets per exit: expected curve P&L per attempt (rank draws)
    rk = R.ranks
    Y = {}
    for hi in EXITS:
        v = np.where(d["FILL"][:, rk], d["PN"][:, rk, hi, 0], 0.0)
        bad = ~np.isfinite(d["PN"][:, 0, hi, 0])
        Y[hi] = np.where(bad, np.nan, np.nanmean(np.where(np.isfinite(v), v, 0.0), axis=1))
    def cal_total(res, cost, q=None):
        if q is None: return R.money(res, cost, A0, B0, True)
        vals = [R.money(res, cost, a, b, True) for a, b in BS[::10]]
        return float(np.percentile(vals, q))
    J = {}; picks_out = {}
    tests = [k for k in days if k - 1 in days and any(dd < k - 1 for dd in days)]
    P(f"test days: {tests}")
    for D in tests:
        tr = us & (day < D - 1); va = us & (day == D - 1); te = us & (day == D)
        E = G.edges_of(X, np.flatnonzero(tr)); B = G.binize(X, E)
        tri = np.flatnonzero(tr); tri = tri[np.argsort(M["bt"][tri])]; cut = int(0.8 * len(tri))
        sc = {}
        for hi in EXITS:
            y = Y[hi]; ok = np.isfinite(y)
            f_ = tri[:cut][ok[tri[:cut]]]; v_ = tri[cut:][ok[tri[cut:]]]
            mdl = G.fit(B, np.clip(np.nan_to_num(y), -0.2, 0.2), f_, v_, loss="l2", rounds=600, lr=0.05, depth=4, min_n=300, lam=10.0, sub=0.8, fsub=0.8, seed=2, patience=60)
            sc[hi] = G.predict(mdl, B)
        # choose exit + threshold on VAL: calibrated, NOW costs, K=3, all leaders
        best = None
        for hi in EXITS:
            for qv in QS:
                th = float(np.quantile(sc[hi][va], qv))
                v = cal_total(R.run(va & (sc[hi] >= th), hi, K=3), "NOW")
                if best is None or v > best[0]: best = (v, hi, th, qv)
        vbest, hi, th, qv = best
        pk = te & (sc[hi] >= th)
        rs = R.run(pk, hi, K=3); c = R.counts(rs)
        row = dict(day=D, exit=R.HS[hi], th=th, q=qv, val_cal=vbest, hours=d["uh"].get(D, 0), picks=int(pk.sum()), **c,
                   ideal=R.money(R.run(pk, hi, K=3, model="ideal"), "NOW"), ours=R.money(rs, "NOW"), cal=cal_total(rs, "NOW"),
                   cal_lo=cal_total(rs, "NOW", 5), cal_hi=cal_total(rs, "NOW", 95),
                   ours_cheap=R.money(rs, "CHEAP"), cal_cheap=cal_total(rs, "CHEAP"), cal_cheap_lo=cal_total(rs, "CHEAP", 5))
        for fi, nm in ((1, "f05"), (2, "f10"), (3, "f20")):
            rr = R.run(pk, hi, K=3, fol=fi); row[nm] = cal_total(rr, "NOW"); row[nm + "_cheap"] = cal_total(rr, "CHEAP")
        # variants at the frozen threshold
        r1 = R.run(pk, hi, K=1); row["k1_cal"] = cal_total(r1, "NOW"); row["k1_fires"] = R.counts(r1)["fires"]; row["k1_cal_cheap"] = cal_total(r1, "CHEAP")
        rn = R.run(pk, hi, K=3, near_only=True); row["near_cal"] = cal_total(rn, "NOW"); row["near_fires"] = R.counts(rn)["fires"]; row["near_cal_cheap"] = cal_total(rn, "CHEAP")
        row["far_share"] = float(1 - d["near"][pk].mean()) if pk.any() else 0
        # each exit with its own VAL-chosen threshold (information; the frozen choice is 'exit')
        for hj in EXITS:
            bj = max(((cal_total(R.run(va & (sc[hj] >= np.quantile(sc[hj][va], q2)), hj, K=3), "NOW"), q2) for q2 in QS))
            thj = float(np.quantile(sc[hj][va], bj[1])); rj = R.run(te & (sc[hj] >= thj), hj, K=3)
            row[f"exit{R.HS[hj]}_val"] = bj[0]; row[f"exit{R.HS[hj]}_cal"] = cal_total(rj, "NOW"); row[f"exit{R.HS[hj]}_cal_cheap"] = cal_total(rj, "CHEAP")
        # earlier-DV8 method on the same picks: ms landing + vshift (s7)
        J[D] = row; picks_out[D] = dict(idx=np.flatnonzero(pk), score=sc[hi][pk], exit=R.HS[hi])
        P(f"D{D}: exit {R.HS[hi]} q{qv} th {th:.4f}: picks {row['picks']} fires {c['fires']:.0f} fills {c['fills']:.0f} | ideal {row['ideal']:+.2f} ours {row['ours']:+.2f} "
          f"cal {row['cal']:+.2f} [{row['cal_lo']:+.2f}..{row['cal_hi']:+.2f}] cheap-cal {row['cal_cheap']:+.2f} | f10 {row['f10']:+.2f} ({time.time() - t0:.0f}s)")
    json.dump(J, open(f"{L.D}/g1.json", "w"), indent=1, default=float)
    pickle.dump(picks_out, open(f"{L.D}/g1_picks.pkl", "wb"))
    # ---------------- tables
    P("\n## DV8 per test day (walk-forward; SOL per day window, usable hours only; K=3, all leaders, guard 1.05, 0.40 SOL)")
    P("| day | hours | exit (val) | picks | fires | fills | wins | ideal NOW | ours NOW | calibrated NOW [5-95%] | conservative NOW | calibrated CHEAP | conservative CHEAP |")
    P("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for D, r in J.items():
        P(f"| {L.day_name(D)} | {r['hours']} | {r['exit']} (q{r['q']}) | {r['picks']:,} | {r['fires']:,.0f} | {r['fills']:,.0f} | {r['wins']:,.0f} | {r['ideal']:+.2f} | {r['ours']:+.2f} | "
          f"{r['cal']:+.2f} [{r['cal_lo']:+.2f}..{r['cal_hi']:+.2f}] | {r['cal_lo']:+.2f} | {r['cal_cheap']:+.2f} | {r['cal_cheap_lo']:+.2f} |")
    P("\n## Fewer-followers stress (calibrated; outside buy SOL after our entry cut by 5/10/20%)")
    P("| day | NOW 0% | NOW -5% | NOW -10% | NOW -20% | CHEAP 0% | CHEAP -5% | CHEAP -10% | CHEAP -20% |"); P("|---|---|---|---|---|---|---|---|---|")
    for D, r in J.items():
        P(f"| D{D} | {r['cal']:+.2f} | {r['f05']:+.2f} | {r['f10']:+.2f} | {r['f20']:+.2f} | {r['cal_cheap']:+.2f} | {r['f05_cheap']:+.2f} | {r['f10_cheap']:+.2f} | {r['f20_cheap']:+.2f} |")
    P("\n## Variants at the frozen threshold (calibrated, NOW / CHEAP)")
    P("| day | K=3 all leaders | K=1 | near-only K=3 | far share of picks | exit 5 | exit 8 | exit 12 | (val-chosen exit) |"); P("|---|---|---|---|---|---|---|---|---|")
    for D, r in J.items():
        P(f"| D{D} | {r['cal']:+.2f} / {r['cal_cheap']:+.2f} | {r['k1_cal']:+.2f} / {r['k1_cal_cheap']:+.2f} | {r['near_cal']:+.2f} / {r['near_cal_cheap']:+.2f} | {100 * r['far_share']:.0f}% | "
          f"{r['exit5_cal']:+.2f} / {r['exit5_cal_cheap']:+.2f} | {r['exit8_cal']:+.2f} / {r['exit8_cal_cheap']:+.2f} | {r['exit12_cal']:+.2f} / {r['exit12_cal_cheap']:+.2f} | {r['exit']} |")
    tot = lambda k: sum(r[k] for r in J.values())
    full = [D for D, r in J.items() if r["hours"] >= 20]
    P(f"\nSum over test days {list(J)}: calibrated NOW {tot('cal'):+.2f}, CHEAP {tot('cal_cheap'):+.2f}; ours NOW {tot('ours'):+.2f}; conservative NOW {tot('cal_lo'):+.2f}")
    if full:
        v = np.array([J[D]["cal"] * 24 / J[D]["hours"] for D in full]); vc = np.array([J[D]["cal_cheap"] * 24 / J[D]["hours"] for D in full])
        P(f"Per 24 h over full test days {full}: calibrated NOW mean {v.mean():+.2f} (min {v.min():+.2f}, max {v.max():+.2f}); CHEAP mean {vc.mean():+.2f} (min {vc.min():+.2f}, max {vc.max():+.2f})")
    open(f"{L.D}/g1.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
