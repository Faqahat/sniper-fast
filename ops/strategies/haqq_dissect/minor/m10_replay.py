#!/usr/bin/env python3
"""MINOR step 10 (read-only): replays of the minor bots' explicit entry rules (m3 MARKET rules, fitted on D0-D2) with the VALIDATED
dv8 machinery (dv8/uni.npz: rank-model landing draws = OUR contention-aware landing, exact curve exits after 5/8/12/30 slots,
follower stress; calibration live = a x model + b per fire, dv8 c2). INFERRED forecasts.
(A) FOR US: rule hits on held-out D3-D5, our landing, 0.40 SOL, at most 3 positions / one per mint; exit chosen on D1-D2 (calibrated
    NOW); fill policy OURS (+5 % guard) or BOT (226/231 band 0.895..1.087 x post-dump price; 244/251 no limit); costs per fill (buy,
    sell) and per failed fire: NOW (1.75, 1.77, 0.53 mSOL), S2 (1.75, 0.28, 0.53; his sell recipe), CHEAP (0.33, 0.33, 0.04);
    followers x1.0 and x0.9. Also his own picks (non-causal ceiling).
(B) HIS STYLE (for the reconciliation): rule hits, rank landing (his dump->buy 40/70/197 ms is close to ours), his limit, his size,
    the exit timer nearest his menu, uncalibrated, his 0.79 mSOL/lot, no position cap; per day vs his real P&L of the bot.
Out: minor/m10.txt, minor/m10.json"""
import json, pickle, sys, collections, heapq
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos")
from g1_walkforward import load, calib_boot
from plib import Out
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/minor"
COST = {"NOW": (0.00175, 0.00177, 0.00053), "S2": (0.00175, 0.00028, 0.00053), "CHEAP": (0.00033, 0.00033, 0.00004)}
HIS = {226: dict(size=0.494, exit=0, band=(0.895, 1.087)), 231: dict(size=0.247, exit=1, band=(0.895, 1.087)),
       244: dict(size=0.247, exit=3, band=None), 251: dict(size=0.30, exit=2, band=None)}
HS = (5, 8, 12, 30)


def run(d, idx_mask, hi, fillm, fol, K=3, size=0.4):
    """per rank draw: list of (fills bool, pn) over the picks taken; chronological greedy, <= K open, one per mint"""
    M = d["M"]; cc = M["cc"]; mint = M["mint"].astype(np.int64); PN = d["PN"]; names = list(d["names"])
    rk = [i for i, n in enumerate(names) if n.startswith("rank")]
    m = idx_mask & np.isfinite(PN[:, rk[0], hi, 0])
    idx = np.flatnonzero(m); idx = idx[np.argsort(cc[idx])]
    hold = HS[hi] * 212.0 + 300.0; out = []
    for ci, c in enumerate(rk):
        pn = PN[idx, c, hi, fol] * size / 0.4; ok = fillm[idx, ci] & np.isfinite(pn)
        if K is None: take = np.ones(len(idx), bool)
        else:
            take = np.zeros(len(idx), bool); heap = []; busy = {}
            for k, i in enumerate(idx):
                t = cc[i]
                while heap and heap[0] <= t: heapq.heappop(heap)
                if len(heap) >= K or busy.get(mint[i], -1.0) > t: continue
                take[k] = True
                if ok[k]: heapq.heappush(heap, t + hold); busy[mint[i]] = t + hold
        out.append((idx[take], ok[take], np.where(ok[take], pn[take], 0.0)))
    return out


def money(res, cost, a=1.0, b=0.0, calib=True, per_lot=None):
    tot = []
    for idx, ok, pn in res:
        n = len(ok); nf = ok.sum()
        g = (a * pn.sum() + b * n) if calib else pn.sum()
        if per_lot is not None: tot.append(g - nf * per_lot)
        else:
            cb, cs, cf = COST[cost]; tot.append(g - nf * (cb + cs) - (n - nf) * cf)
    return float(np.mean(tot))


def main():
    P = Out(f"{OUT}/m10.txt")
    d = load(); use = d["usable"]; day = d["day"]
    (A0, B0), BS = calib_boot()
    names = list(d["names"]); rk = [i for i, n in enumerate(names) if n.startswith("rank")]
    PR = d["PR"]; FILL = d["FILL"]
    Z = pickle.load(open(f"{OUT}/m3.pkl", "rb")); Y = Z["Y"]; YN = Z["YN"]; res = Z["res"]
    lots = pickle.load(open(f"{OUT}/m2_lots.pkl", "rb"))
    real = collections.defaultdict(float)
    for l in lots: real[(l["code"], l["day"])] += l["net"]
    P(f"# Minor-bot rule replays (dv8 machinery; calibration live = {A0:.2f} x model {1000 * B0:+.2f} mSOL/fire). INFERRED.")
    J = {}
    for c, cfg in HIS.items():
        if (c, "MARKET") not in res: continue
        rule = res[(c, "MARKET")]["mask"] & use
        conds = res[(c, "MARKET")]["conds"]
        P(f"\n## code {c}: MARKET rule (fitted D0-D2): " + " AND ".join(f"{n} {s} {t:.3g}" for n, t, s in conds))
        fills = {"OURS": FILL[:, rk]}
        if cfg["band"]:
            lo, hi_ = cfg["band"]; fills["BOT"] = (PR[:, rk] <= hi_) & (PR[:, rk] >= lo)
        else:
            fills["BOT"] = np.ones((len(PR), len(rk)), bool)
        # (A) FOR US
        P("| picks | fill | exit (chosen D1-D2) | day | fires | fills | model NOW | calibrated NOW | calibrated S2 | calibrated CHEAP | cal. NOW, 10% fewer followers | cal. CHEAP, 10% fewer |")
        P("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for pick_name, pick in (("rule", rule), ("his picks (ceiling)", Y[c] & use)):
            for fname, fm in fills.items():
                # exit choice on D1-D2
                best = None
                for hi in range(4):
                    v = sum(money(run(d, pick & (day == dd), hi, fm, 0), "NOW", A0, B0) for dd in (1, 2))
                    if best is None or v > best[0]: best = (v, hi)
                hi = best[1]; tots = collections.defaultdict(float)
                for dd in (3, 4, 5):
                    r0 = run(d, pick & (day == dd), hi, fm, 0); r9 = run(d, pick & (day == dd), hi, fm, 2)
                    row = dict(fires=np.mean([len(x[1]) for x in r0]), fills=np.mean([x[1].sum() for x in r0]), model=money(r0, "NOW", calib=False),
                               now=money(r0, "NOW", A0, B0), s2=money(r0, "S2", A0, B0), cheap=money(r0, "CHEAP", A0, B0),
                               now9=money(r9, "NOW", A0, B0), cheap9=money(r9, "CHEAP", A0, B0))
                    for k, v in row.items(): tots[k] += v
                    J[f"{c}|{pick_name}|{fname}|D{dd}"] = row
                    P(f"| {pick_name} | {fname} | {HS[hi]} slots | D{dd} | {row['fires']:.0f} | {row['fills']:.0f} | {row['model']:+.2f} | {row['now']:+.2f} | {row['s2']:+.2f} | {row['cheap']:+.2f} | {row['now9']:+.2f} | {row['cheap9']:+.2f} |")
                P(f"| {pick_name} | {fname} | {HS[hi]} slots | **D3-D5** | {tots['fires']:.0f} | {tots['fills']:.0f} | {tots['model']:+.2f} | **{tots['now']:+.2f}** | {tots['s2']:+.2f} | {tots['cheap']:+.2f} | {tots['now9']:+.2f} | {tots['cheap9']:+.2f} |")
        # (B) HIS STYLE per day (all days; D0-D2 in-sample for the rule)
        P(f"\nHIS-STYLE replay of the rule (his size {cfg['size']}, his limit, exit {HS[cfg['exit']]} slots, his 0.79 mSOL/lot, uncalibrated) vs his real net for code {c}:")
        P("| day | rule picks | his-style rule replay SOL | his real net (all lots of the code) | his net on dumps he bought that the rule catches |")
        P("|---|---|---|---|---|")
        for dd in range(6):
            r = run(d, rule & (day == dd), cfg["exit"], fills["BOT"], 0, K=None, size=cfg["size"])
            v = money(r, None, calib=False, per_lot=0.00079)
            caught = YN[c][(rule & Y[c] & (day == dd))].sum()
            J[f"{c}|hisstyle|D{dd}"] = dict(rep=v, real=real[(c, dd)], caught=float(caught), picks=int((rule & (day == dd)).sum()))
            P(f"| D{dd}{' (in-sample)' if dd <= 2 else ''} | {int((rule & (day == dd)).sum())} | {v:+.2f} | {real[(c, dd)]:+.2f} | {caught:+.2f} |")
    json.dump(J, open(f"{OUT}/m10.json", "w"), indent=1)
    P.save()


if __name__ == "__main__":
    main()
