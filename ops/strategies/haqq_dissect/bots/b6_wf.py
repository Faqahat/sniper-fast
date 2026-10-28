#!/usr/bin/env python3
"""BOTS step 6 (read-only): 'our 247' / 'our 248' walk-forward. For test day D: imitation score from the model trained on days < D (b3, TAPE
features only = nothing about haqq), config (probability threshold, guard none / +5 %, exit) chosen on day D-1 ONLY (its own OOS
scores), then day D read once. Replay values = b5 (every universe dump at our regular landing, 4 rank draws, haqq kept in the tape).
Calibration per (guard, exit, followers) = OLS of our REAL-position replay on the rank-model replay over our 1,544 live fires (b4 'fire'
events; real position MEASURED); conservative = 5 % bootstrap quantile. The old dv8 calibration 0.61 x - 1.17 mSOL is shown too.
Costs per fill / per failed fire (SOL): NOW 0.00352 / 0.00053 (MEASURED), S2 0.00186 / 0.00036 (analyst D's S2: S1 buy -0.17 mSOL, his
sell recipe 0.28), CHEAP 0.00079 / 0.00004 (haqq's measured 0.79 mSOL/lot).
Rows: model ('ours', uncalibrated), calibrated, conservative; followers -10 / -20 %; K = 1 / 3 / unlimited open positions; near-only.
Out: bots/b6.txt, b6.json, b6_picks.pkl"""
import sys, json, pickle, heapq, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/bots"
COST = {"NOW": (0.00352, 0.00053), "S2": (0.00186, 0.00036), "CHEAP": (0.00079, 0.00004)}
THR = (0.02, 0.03, 0.05, 0.08, 0.12, 0.17, 0.25, 0.35, 0.5, 0.65)
BUSY = {"('T', 5)": 5 * 212 + 300, "('RIDE', 150, 300, 2000)": 2300, "('RIDE', 150, 150, 1000)": 1300, "('MS', 200)": 500, "('MS', 1000)": 1300,
        "('MS', 2000)": 2300, "('MS', 4000)": 4300, "('RIDE', 424, 1000, 10000)": 10300}
lines = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); lines.append(s)


def calibration(PLs):
    """(guard, pi, fi) -> (a, b, a5, b5 conservative pair) from b4 fire events"""
    Z = pickle.load(open(f"{OUT}/b4_res.pkl", "rb")); meta, res, PL4 = Z["meta"], Z["res"], Z["PL"]
    fid = [i for i, m in meta.items() if m["kind"] == "fire" and res.get(i)]
    out = {}
    g = np.random.default_rng(9)
    bidx = [g.integers(0, len(fid), len(fid)) for _ in range(500)]
    for guard in ("none", "g5"):
        for pi, pol in enumerate(PLs):
            a4 = [str(p) for p in PL4].index(pol)
            for fi in range(3):
                y = np.array([(res[i][0]["pn"][fi, a4] if (guard == "none" or res[i][0]["fill5"]) else 0.0) for i in fid])
                x = np.array([np.mean([(e["pn"][fi, a4] if (guard == "none" or e["fill5"]) else 0.0) for e in res[i][1:]]) for i in fid])
                A = np.vstack([x, np.ones(len(x))]).T
                a, b = np.linalg.lstsq(A, y, rcond=None)[0]
                bs = np.array([np.linalg.lstsq(A[ii], y[ii], rcond=None)[0] for ii in bidx])
                out[(guard, pi, fi)] = (a, b, bs, float(y.mean()), float(x.mean()))
    return out


def main():
    t0 = time.time()
    B5 = np.load(f"{OUT}/b5.npz"); PN = B5["PN"]; F5 = B5["F5"]; sel = B5["sel"]; PLs = [str(x) for x in B5["PL"]]
    SC = np.load(f"{OUT}/b3_scores.npz")
    Z2 = np.load(f"{OUT}/b2.npz"); day = Z2["day"]
    U = np.load(f"{L.D}/uni.npz"); M = U["M"]; near = U["near"]; cc = M["cc"]; mint = M["mint"].astype(np.int64)
    CAL = calibration(PLs)
    P("# Calibration per exit (our 1,544 live fires: REAL-position replay vs rank-model replay, fol 1.0; mSOL per fire)")
    P("| guard | exit | real mean | rank mean | a | b mSOL | a (5-95%) |"); P("|---|---|---|---|---|---|---|")
    for (guard, pi, fi), (a, b, bs, ym, xm) in CAL.items():
        if fi: continue
        P(f"| {guard} | {PLs[pi]} | {1000 * ym:+.2f} | {1000 * xm:+.2f} | {a:.2f} | {1000 * b:+.2f} | {np.percentile(bs[:, 0], 5):.2f}..{np.percentile(bs[:, 0], 95):.2f} |")

    def vals(m, si, gi, pi, fi):
        """per pick x draw: fill bool, pn (0 if no fill)"""
        idx = np.flatnonzero(m)
        f = np.ones((len(idx), PN.shape[1]), bool) if gi == "none" else F5[idx, :, si]
        pn = np.where(f, PN[idx, :, si, fi, pi], 0.0)
        pn = np.nan_to_num(pn)
        return idx, f, pn

    def money(f, pn, cost, cal=None):
        cf, cx = COST[cost]
        n = f.shape[0]
        if cal is None: g = pn.sum(0)
        else: a, b = cal; g = a * pn.sum(0) + b * n
        return float(np.mean(g - f.sum(0) * cf - (n - f.sum(0)) * cx))

    def greedy(idx, f, K, busy):
        """per draw: keep mask under at most K open positions, one per mint (unfilled attempts don't occupy)"""
        o = np.argsort(cc[idx]); keep = np.zeros(f.shape, bool)
        for d in range(f.shape[1]):
            heap = []; bm = {}
            for j in o:
                t = cc[idx[j]]
                while heap and heap[0] <= t: heapq.heappop(heap)
                mt = mint[idx[j]]
                if (K is not None and len(heap) >= K) or bm.get(mt, -1) > t: continue
                keep[j, d] = True
                if f[j, d]: heapq.heappush(heap, t + busy); bm[mt] = t + busy
        return keep

    J = {}; PICKS = {}
    for bot, si in ((247, 1), (248, 0)):
        s = SC[f"{bot}_TAPE"]; pr = 1 / (1 + np.exp(-np.nan_to_num(s, nan=-50)))
        y = Z2[f"Y{bot}"]; hn = Z2[f"N{bot}"]
        P(f"\n# Bot {bot} imitation gate, size {(0.30, 0.40)[si]:.2f} SOL; config chosen on D-1 per cost level")
        for cost in ("NOW", "S2", "CHEAP"):
            P(f"\n## {bot} / {cost} costs: SOL per test day (usable hours)")
            P("| day | config (p>=, guard, exit) | val | picks | his picks among them | fills | model | calibrated [5-95% boot] | conservative | fol -10% cal | fol -20% cal | K=1 cal | K=3 cal | near-only cal | old 0.61/-1.17 cal |")
            P("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
            for D in (2, 3, 4, 5, 6):
                va = sel & (day == D - 1) & np.isfinite(s); te = sel & (day == D) & np.isfinite(s)
                best = None
                for th in THR:
                    for gi in ("none", "g5"):
                        for pi in range(len(PLs)):
                            m = va & (pr >= th)
                            if m.sum() < 20: continue
                            a, b = CAL[(gi, pi, 0)][:2]
                            idx, f, pn = vals(m, si, gi, pi, 0)
                            v = money(f, pn, cost, (a, b))
                            if best is None or v > best[0]: best = (v, th, gi, pi)
                if best is None: continue
                v, th, gi, pi = best
                m = te & (pr >= th)
                idx, f, pn = vals(m, si, gi, pi, 0)
                a, b, bs = CAL[(gi, pi, 0)][:3]
                r = dict(day=D, th=th, guard=gi, exit=PLs[pi], val=v, picks=int(m.sum()), his=int(y[m].sum()), his_net=float(hn[m].sum()), fills=float(f.sum(0).mean()),
                         model=money(f, pn, cost), cal=money(f, pn, cost, (a, b)))
                cons = [money(f, pn, cost, tuple(bb)) for bb in bs[::5]]; r["cons"] = float(np.percentile(cons, 5))
                # bootstrap over picks of the calibrated total
                per = a * pn.mean(1) + b - f.mean(1) * COST[cost][0] - (1 - f.mean(1)) * COST[cost][1]
                g = np.random.default_rng(1); bt = [per[g.integers(0, len(per), len(per))].sum() for _ in range(1000)] if len(per) else [0]
                r["lo"], r["hi"] = float(np.percentile(bt, 5)), float(np.percentile(bt, 95))
                for fi, nm in ((1, "f10"), (2, "f20")):
                    i2, f2, p2 = vals(m, si, gi, pi, fi); r[nm] = money(f2, p2, cost, CAL[(gi, pi, fi)][:2])
                for K, nm in ((1, "k1"), (3, "k3")):
                    kp = greedy(idx, f, K, BUSY[PLs[pi]])
                    cf, cx = COST[cost]
                    r[nm] = float(np.mean([a * (pn[kp[:, d], d]).sum() + b * kp[:, d].sum() - (f[kp[:, d], d]).sum() * cf - (kp[:, d].sum() - f[kp[:, d], d].sum()) * cx for d in range(f.shape[1])]))
                mn = m & near; i3, f3, p3 = vals(mn, si, gi, pi, 0); r["near"] = money(f3, p3, cost, (a, b))
                r["old"] = money(f, pn, cost, (0.61, -0.00117))
                J[f"{bot}_{cost}_{D}"] = r
                PICKS[(bot, cost, D)] = dict(idx=idx, th=th, guard=gi, exit=PLs[pi], pi=pi, si=si, a=a, b=b, p=pr[idx])
                P(f"| D{D} | p>={th} {gi} {PLs[pi]} | {v:+.2f} | {r['picks']:,} | {r['his']:,} ({100 * r['his'] / max(r['picks'], 1):.0f}%, his net {r['his_net']:+.2f}) | {r['fills']:.0f} | "
                  f"{r['model']:+.2f} | {r['cal']:+.2f} [{r['lo']:+.2f}..{r['hi']:+.2f}] | {r['cons']:+.2f} | {r['f10']:+.2f} | {r['f20']:+.2f} | {r['k1']:+.2f} | {r['k3']:+.2f} | {r['near']:+.2f} | {r['old']:+.2f} |")
            full = [J[f"{bot}_{cost}_{D}"] for D in (2, 3, 4, 5) if f"{bot}_{cost}_{D}" in J]
            P(f"- {bot} {cost}: D2-D5 calibrated sum {sum(r['cal'] for r in full):+.2f} SOL ({sum(r['cal'] for r in full) / max(len(full), 1):+.2f}/day, days > 0: {sum(r['cal'] > 0 for r in full)}/{len(full)}); "
              f"conservative {sum(r['cons'] for r in full):+.2f}; fol -10% {sum(r['f10'] for r in full):+.2f}; model {sum(r['model'] for r in full):+.2f}")
        print(f"{bot} done ({time.time() - t0:.0f}s)", flush=True)
    # ---- oracle rows: HIS exact picks at our landing (perfect imitation), every config fixed
    P("\n# Oracle (information only, not tradable): his exact picks at OUR landing (haqq kept in the tape), SOL/day, D2-D5 mean")
    P("| bot | guard | exit | model NOW | cal NOW | cal S2 | cal CHEAP | cal CHEAP fol -10% | his own net/day on them |"); P("|---|---|---|---|---|---|---|---|---|")
    for bot, si in ((247, 1), (248, 0)):
        y = Z2[f"Y{bot}"]; hn = Z2[f"N{bot}"]
        for gi in ("none", "g5"):
            for pi in range(len(PLs)):
                tot = {k: [] for k in ("m", "n", "s", "c", "c10", "h")}
                for D in (2, 3, 4, 5):
                    m = sel & (day == D) & y
                    idx, f, pn = vals(m, si, gi, pi, 0); a, b = CAL[(gi, pi, 0)][:2]
                    tot["m"].append(money(f, pn, "NOW")); tot["n"].append(money(f, pn, "NOW", (a, b))); tot["s"].append(money(f, pn, "S2", (a, b)))
                    tot["c"].append(money(f, pn, "CHEAP", (a, b)))
                    i2, f2, p2 = vals(m, si, gi, pi, 1); tot["c10"].append(money(f2, p2, "CHEAP", CAL[(gi, pi, 1)][:2])); tot["h"].append(float(hn[m].sum()))
                P(f"| {bot} | {gi} | {PLs[pi]} | " + " | ".join(f"{np.mean(tot[k]):+.2f}" for k in ("m", "n", "s", "c", "c10", "h")) + " |")
    json.dump(J, open(f"{OUT}/b6.json", "w"), indent=1, default=float)
    pickle.dump(PICKS, open(f"{OUT}/b6_picks.pkl", "wb"))
    open(f"{OUT}/b6.txt", "w").write("\n".join(lines) + "\n")
    print(f"done ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
