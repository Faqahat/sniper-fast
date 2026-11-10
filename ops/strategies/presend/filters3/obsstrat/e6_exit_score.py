#!/usr/bin/env python3
"""OBS-STRAT EXIT125 scorer (ESTIMATE: tape replay of our own sell; no realized P&L can exist for a changed exit).
Rule: --presend-live-exit-ms 125 instead of 200. Model: the engine's timer overshoot is kept, so a "time-ms" exit decided at real T
moves to T - 75 ms (never before our fill is seen + 1 ms). A TP / SL / time-limit exit decided later than our fill seen + 147 ms
(= 125 + the median 22 ms overshoot) becomes a timer exit at fill seen + 147 ms. The sell lands after this position's own measured
decision->landing delay L ("own"), or, as a check, after each decile of the period's L ("deciles": both the real and the new time
replayed with the same L set, model vs model). Positions without a single-buy/single-sell hold tape are unchanged (counted).
Change in P&L = change in gross curve proceeds x (1 - 1.25% sell fee).
usage: e6_exit_score.py ROWS.jsonl [--shift-ms -75] [--hours DEV=74.35,VAL=20.61] [--json OUT]"""
import sys, json, collections, argparse
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/filters3/obsstrat")
import tlib
ap = argparse.ArgumentParser(); ap.add_argument("rows"); ap.add_argument("--shift-ms", type=float, default=-75.0)
ap.add_argument("--hours", default="DEV=74.35,VAL=20.61"); ap.add_argument("--json")
A = ap.parse_args(); HRS = {k: float(v) for k, v in (x.split("=") for x in A.hours.split(","))}
S = A.shift_ms * 1e6; TCAP = (200 + A.shift_ms + 22) * 1e6
rows = list(tlib.load(A.rows)); P = [(d, tlib.Pos(d)) for d in rows]
Ls = collections.defaultdict(list)
for d, p in P:
    if p.ok: Ls[d["per"]].append(p.L)
Q = {k: [sorted(v)[int(len(v) * q / 10)] for q in range(1, 10)] for k, v in Ls.items()}
def new_T(p):
    if p.why == "time-ms": return max(p.T + S, p.tfill + 1e6)
    return p.tfill + TCAP if p.T > p.tfill + TCAP else None
res = {}
for per in HRS:
    ds = [(d, p) for d, p in P if d["per"] == per]
    ch_own, ch_dec, base, after, n_ch, n_rep = [], [], 0.0, [], 0, 0
    runs = collections.defaultdict(float)
    for d, p in ds:
        base += d["pnl"]; dd = de = 0.0
        if p.ok:
            n_rep += 1; T = new_T(p)
            if T is not None:
                n_ch += 1
                Te = min(T, p.tape_end_t() - p.L)
                cf, _ = p.proceeds_at(Te); dd = (cf - p.act) * (1 - tlib.FEE_SELL) / 1e9
                for L in Q[per]:
                    b0, _ = p.proceeds_at(p.T, L); Tl = min(T, p.tape_end_t() - L); c1, _ = p.proceeds_at(Tl, L)
                    de += (c1 - b0) * (1 - tlib.FEE_SELL) / 1e9 / len(Q[per])
        ch_own.append(dd); ch_dec.append(de); after.append(d["pnl"] + dd); runs[d["run"]] += dd
    top5 = sorted(range(len(ds)), key=lambda i: -ds[i][0]["pnl"])[:5]
    r = dict(n=len(ds), replayable=n_rep, changed=n_ch, base=round(base, 3), base_win=round(sum(d["pnl"] > 0 for d, _ in ds) / max(len(ds), 1), 3),
             gain_own=round(sum(ch_own), 3), gain_own_day=round(sum(ch_own) / HRS[per] * 24, 2),
             gain_own_wo_its5best=round(sum(sorted(ch_own, reverse=True)[5:]), 3),
             gain_own_wo_top5_trades=round(sum(ch_own) - sum(ch_own[i] for i in top5), 3),
             gain_deciles=round(sum(ch_dec), 3), gain_deciles_day=round(sum(ch_dec) / HRS[per] * 24, 2),
             after_win_own=round(sum(x > 0 for x in after) / max(len(after), 1), 3), per_run_own={k: round(v, 3) for k, v in runs.items()})
    res[per] = r
    print(per, json.dumps(r))
if A.json: json.dump(res, open(A.json, "w"), indent=1)
