#!/usr/bin/env python3
"""REARM step 5 (read-only): tables from res_D<k>_<tag>.pkl (r4_days.py). INFERRED (replay) numbers; the calibration levels come
from the validation (r2b_valtable.py, MEASURED live vs replay on AMS r24-r33 + FRA r26):
  model        = the replay as is;
  calibrated   = every fill's P&L - 1.49 mSOL (pooled live - replay per fill), failed-try fees as replayed (live/replay 1.00);
  conservative = every fill's P&L - 4.18 mSOL (the 5th pct of the run bootstrap of that gap).
Costs per fill: NOW = buy fee 5,120 + helius-ps tip 200,000 + sell fee 605,000 + sell tips 1,200,000 + ATA close 5,020 lamports
(2.015 mSOL, the live pre-send fill); S2 = sells ~0.3 mSOL (analyst D) -> 0.510 mSOL. Failed tries 5,120 each.
Exits: 'base' = live (TP 10 % / SL 20 % / 2 slots); 'wave' = analyst C's short wave exit; followers: all / 10 % / 20 % fewer.
ADDED = (base + re-arm) - base over every window (common random numbers): includes the knock-on on normal windows.
usage: r5_tables.py TAG [--days 0,1,2,3,4,5,6] [--fixed cfg,cfg] [--out name]"""
import sys, os, pickle, argparse, collections, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L

OUT = "/home/moiz/sniper-data/haqq_dissect/rearm"
COST = {"NOW": 5120 + 200_000 + 605_000 + 1_200_000 + 5020, "S2": 5120 + 200_000 + 300_000 + 5020}
SHIFT = {"model": 0.0, "cal": 1.49e6, "cons": 4.18e6}
FAIL = 5120


def tot(rows, kind=None, exit_="base", fol="", cost="NOW", lvl="cal"):
    """-> dict: windows armed, fills, wins, fill P&L, fees, net (SOL) over rows (one draw)"""
    v = ("base" if fol == "" else "cut" + fol) if exit_ == "base" else "wave" + fol
    n = f = w = 0; pf = fee = 0.0
    for r in rows:
        if kind and r[0][0] != kind: continue
        if not r[1]: continue
        n += 1; fee += r[4] * FAIL
        if r[3]:
            g = r[8][2][v][0] - COST[cost] - SHIFT[lvl]
            f += 1; pf += g; w += g > 0
    return dict(n=n, f=f, w=w, pf=pf / 1e9, fee=fee / 1e9, net=(pf - fee) / 1e9)


def added(res, name, d=0, **kw):
    b = tot(res["out"]["base"][d], **kw); c = tot(res["out"][name][d], **kw)
    return {k: c[k] - b[k] for k in b}, b, c


def load(day, tag):
    fn = f"{OUT}/res_D{day}_{tag}.pkl"
    return pickle.load(open(fn, "rb")) if os.path.exists(fn) else None


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("tag"); ap.add_argument("--days", default="0,1,2,3,4,5,6"); ap.add_argument("--fixed", default="0.02:50:120:2:0")
    ap.add_argument("--out", default=None)
    A = ap.parse_args()
    days = [int(x) for x in A.days.split(",")]
    R = {d: load(d, A.tag) for d in days}; R = {d: r for d, r in R.items() if r}
    Lout = []
    def P(s=""): print(s, flush=True); Lout.append(s)
    names = [n for n in next(iter(R.values()))["out"] if n != "base"]
    P(f"# RE-ARM replay '{A.tag}': engine rules (rsim.run_x), base = live pre-send now (k8, 40/s, 0.40 SOL, QUIET stop 6:2). INFERRED.")
    P("Config = X (paid: r2 >= X SOL on a 0.40 buy; any = no check) : G (window slots) : A (max token age s at the paid dump) : K (tries / pace slot) : H (needs a >= 6 % holder)")
    # 1. walk-forward: choose on D-1 by ADDED calibrated NOW (live exit), test D
    P("\n## 1. Walk-forward (config chosen on the previous day by added calibrated SOL, NOW costs, live exit; tested on the day)")
    P("| Test day | Chosen | Re windows armed | Re fills (wins) | Added fills | Added net model | **calibrated** | conservative | failed-try fees added | -10 % followers (cal) | -20 % (cal) | S2 costs (cal) | wave exit (cal) | wave + S2 (cal) |")
    P("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    S = collections.defaultdict(float)
    for d in days:
        if d not in R or d - 1 not in R: continue
        best = max(names, key=lambda n: added(R[d - 1], n, lvl="cal")[0]["net"])
        res = R[d]
        a = {lv: added(res, best, lvl=lv)[0] for lv in SHIFT}
        re_ = tot(res["out"][best][0], kind="re", lvl="cal")
        f10 = added(res, best, fol="10", lvl="cal")[0]["net"]; f20 = added(res, best, fol="20", lvl="cal")[0]["net"]
        s2 = added(res, best, cost="S2", lvl="cal")[0]["net"]; wv = added(res, best, exit_="wave", lvl="cal")[0]["net"]
        wv2 = added(res, best, exit_="wave", cost="S2", lvl="cal")[0]["net"]
        P(f"| {L.day_name(d)} | {best} | {re_['n']:,} | {re_['f']} ({re_['w']}) | {a['cal']['f']:+d} | {a['model']['net']:+.2f} | **{a['cal']['net']:+.2f}** | {a['cons']['net']:+.2f} | {a['cal']['fee']:+.3f} | {f10:+.2f} | {f20:+.2f} | {s2:+.2f} | {wv:+.2f} | {wv2:+.2f} |")
        if 2 <= d <= 5:
            for k, v in (("model", a["model"]["net"]), ("cal", a["cal"]["net"]), ("cons", a["cons"]["net"]), ("f10", f10), ("f20", f20), ("s2", s2), ("wv", wv), ("wv2", wv2)): S[k] += v
    P(f"\nSum D2-D5 (the days analyst A reported): model {S['model']:+.2f}, calibrated {S['cal']:+.2f}, conservative {S['cons']:+.2f}, -10% {S['f10']:+.2f}, -20% {S['f20']:+.2f}, S2 {S['s2']:+.2f}, wave {S['wv']:+.2f}, wave+S2 {S['wv2']:+.2f} SOL")
    # 2. fixed configs every day
    for fx in A.fixed.split(","):
        if fx not in names: continue
        P(f"\n## 2. Fixed config {fx} on every day (ADDED vs base; SOL)")
        P("| Day | Re windows armed | why ended | Re fills (wins) | re mSOL/fill cal | Added fills | Added model | **calibrated** | conservative | fees added | -10 % | -20 % | S2 | wave | wave + S2 | normal windows' change (cal) |")
        P("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for d in days:
            if d not in R: continue
            res = R[d]; rows = res["out"][fx][0]
            a = {lv: added(res, fx, lvl=lv)[0] for lv in SHIFT}
            re_ = tot(rows, kind="re", lvl="cal")
            whys = collections.Counter(r[2] for r in rows if r[0][0] == "re")
            t2c = tot(rows, kind="t2", lvl="cal")["net"] - tot(res["out"]["base"][0], kind="t2", lvl="cal")["net"]
            P(f"| {L.day_name(d)} | {re_['n']:,} | " + ", ".join(f"{k} {v}" for k, v in whys.most_common(5)) + f" | {re_['f']} ({re_['w']}) | {1000 * re_['pf'] / max(re_['f'], 1):+.2f} | {a['cal']['f']:+d} | {a['model']['net']:+.2f} | **{a['cal']['net']:+.2f}** | {a['cons']['net']:+.2f} | "
              f"{a['cal']['fee']:+.3f} | {added(res, fx, fol='10')[0]['net']:+.2f} | {added(res, fx, fol='20')[0]['net']:+.2f} | {added(res, fx, cost='S2')[0]['net']:+.2f} | "
              f"{added(res, fx, exit_='wave')[0]['net']:+.2f} | {added(res, fx, exit_='wave', cost='S2')[0]['net']:+.2f} | {t2c:+.2f} |")
    # 3. the best config per day (in-sample) and the grid's spread: is ANY config positive?
    P("\n## 3. Grid spread per day (ADDED calibrated NOW, live exit; in-sample, for context only)")
    P("| Day | configs > 0 | best (in-sample) | worst | median |")
    P("|---|---|---|---|---|")
    for d in days:
        if d not in R: continue
        v = {n: added(R[d], n, lvl="cal")[0]["net"] for n in names}
        b = max(v, key=v.get); w = min(v, key=v.get)
        P(f"| {L.day_name(d)} | {sum(x > 0 for x in v.values())} of {len(v)} | {b} {v[b]:+.2f} | {w} {v[w]:+.2f} | {np.median(list(v.values())):+.2f} |")
    # base itself
    P("\n## 4. Base (live pre-send now) per day, for scale (calibrated NOW): windows armed / fills / net")
    for d in days:
        if d not in R: continue
        b = tot(R[d]["out"]["base"][0], lvl="cal"); m = tot(R[d]["out"]["base"][0], lvl="model")
        P(f"- {L.day_name(d)}: {b['n']:,} windows, {b['f']} fills, model {m['net']:+.2f}, calibrated {b['net']:+.2f} SOL (fees {b['fee']:.3f})")
    if A.out: open(f"{OUT}/{A.out}", "w").write("\n".join(Lout) + "\n")
