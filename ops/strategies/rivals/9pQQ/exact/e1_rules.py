#!/usr/bin/env python3
"""H3: simple exact exit rules, teacher-forced on its real trips. For every trip the rule is evaluated on each outside trade after its
buy (from slot buy+2: it never sells earlier) up to 3000 slots; predicted sell slot = slot of the first firing row (it reacts in-slot).
Score: share of trips with |pred - real sell slot| <= 1 (hit), share fired earlier / later, and P(hit) for a random-timing baseline
(rule replaced by 'fires on the k-th outside trade' with k matched in distribution is not meaningful) -> we report against the trivial
'sell on the next outside sell' rule.  Train 10-28+10-30 grid, choose on 10-31, test 11-02 (only with 'final').  -> e1_rules.json"""
import sys, json, itertools
import numpy as np
import xlib as X, tlib9 as L
FINAL = "final" in sys.argv
def trips_rows(t):
    """per trip: arrays of the outside rows after the buy (slot >= bs+2, <= bs+3000) and the real sell slot"""
    out = []
    ob, os_ = t.ob, t.os
    pos_s = {}
    for k in os_: pos_s.setdefault(int(t.m[k]), []).append(int(k))
    for b in ob:
        m = int(t.m[b]); ss = [k for k in pos_s.get(m, []) if k > b]
        if not ss: continue
        js = ss[0]; a1 = t.mstart[m + 1]; bs = int(t.s[b])
        hi = int(np.searchsorted(t.s[b:a1], bs + 3000, "right")) + b
        rows = np.arange(b + 1, hi); rows = rows[~t.own[rows] & (t.s[rows] >= bs + 2)]
        out.append((b, js, rows))
    return out
def feats(t, b, rows):
    vb = L.vsol(float(t.cpost[b])); v = L.vsol(t.cpost[rows].astype(float))
    side = np.sign(t.tok[rows]); size = np.abs(t.sol[rows]) / 1e9
    S = t.s[rows]
    ret = v / vb - 1; peak = np.maximum.accumulate(np.r_[vb, v])[1:]; dd = v / peak - 1
    flow = np.cumsum(np.where(side > 0, size, -size))
    # slots since last outside buy (at or before this row), counting the buy row as the start
    lb = np.where(side > 0, S, -1); lb = np.maximum.accumulate(np.r_[int(t.s[b]), lb])[1:]
    nob = S - lb
    return dict(S=S, side=side, size=size, ret=ret, dd=dd, flow=flow, nob=nob, hold=S - int(t.s[b]))
RULES = {
    "sell>=X": [0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0],
    "no_buy_K_slots": [2, 3, 5, 8, 12, 20, 30, 50],
    "ret<=-SL": [0.02, 0.05, 0.1, 0.15, 0.2, 0.3],
    "ret>=TP": [0.05, 0.1, 0.2, 0.3, 0.5],
    "dd_from_peak>=x": [0.03, 0.05, 0.1, 0.15, 0.2, 0.3],
    "flow_since_buy<=-Y": [0.1, 0.3, 0.5, 1.0, 2.0, 3.0],
    "hold>=H": [5, 10, 25, 50, 100, 250, 750],
}
def fire(F, rule, p):
    if rule == "sell>=X": return (F["side"] < 0) & (F["size"] >= p)
    if rule == "no_buy_K_slots": return F["nob"] >= p
    if rule == "ret<=-SL": return F["ret"] <= -p
    if rule == "ret>=TP": return F["ret"] >= p
    if rule == "dd_from_peak>=x": return F["dd"] <= -p
    if rule == "flow_since_buy<=-Y": return F["flow"] <= -p
    if rule == "hold>=H": return F["hold"] >= p
def score(run):
    t = X.load(run); TR = trips_rows(t); res = {}
    cache = [(b, js, feats(t, b, rows)) for b, js, rows in TR if len(rows)]
    for rule, ps in RULES.items():
        for p in ps:
            hit = early = late = never = 0
            for b, js, F in cache:
                f = fire(F, rule, p); ss = int(t.s[js])
                if not f.any(): never += 1; continue
                ps_ = int(F["S"][np.argmax(f)])
                if abs(ps_ - ss) <= 1: hit += 1
                elif ps_ < ss: early += 1
                else: late += 1
            n = len(cache); res[f"{rule}|{p}"] = dict(hit=round(hit / n, 4), early=round(early / n, 4), late=round(late / n, 4), never=round(never / n, 4))
    # combos of the best 2 single rules (OR)
    return res, cache, t
out = {}
for r in X.RUNS[:3] + (X.RUNS[3:] if FINAL else []):
    res, cache, t = score(r); out[X.DAY[r]] = res
    best = sorted(res.items(), key=lambda kv: -kv[1]["hit"])[:8]
    print(X.DAY[r], "trips", len(cache), [(k, v["hit"], v["early"], v["late"]) for k, v in best], flush=True)
json.dump(out, open("e1_rules.json", "w"), indent=1)
