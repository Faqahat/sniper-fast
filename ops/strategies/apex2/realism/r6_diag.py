#!/usr/bin/env python3
"""APEX-REALISM r6: where the realistic edge comes from (contestedness buckets), skip-contested variant (creator history),
realistic-label watchlist."""
import collections, numpy as np
from r5_score import *
pr = print
def bucket_table(nm, mints, z, e, guard, days):
    pr(f"\n### {nm} by first-rival clock (rival = other buy >= 0.05 SOL after the create bundle; our clock median 0.37 slot)\n"
       "| first rival lands | picks/d | P(land) | SOL/day old sim (A) | SOL/day M1 | share of old-sim profit |\n|---|---|---|---|---|---|")
    hrs = sum(HRS[d] for d in days); B = ((0, .06, "< 0.06 slot (instant / creator wallets)"), (.06, .37, "0.06-0.37"), (.37, 1.0, "0.37-1.0"),
                                          (1.0, 8.9, "> 1 slot"), (8.9, 99, "none within 3 slots"))
    tot_a = sum(net(m, z, e, "A", guard)[0] for m in mints if INFO[m]["day"] in days)
    for lo, hi, lab in B:
        ms = [m for m in mints if INFO[m]["day"] in days and lo <= S[m][1]["rc"] < hi]
        a = sum(net(m, z, e, "A", guard)[0] for m in ms); b = [net(m, z, e, "M1", guard) for m in ms]
        pr(f"| {lab} | {len(ms)*24/hrs:.0f} | {np.mean([x[1] for x in b]) if b else 0:.2f} | {a*24/hrs:+.2f} | {sum(x[0] for x in b)*24/hrs:+.2f} | {a/tot_a:.0%} |")
bucket_table("APEX-3 0.4 w0.4_6.0, guard first, days 2..7", AP3, 0.4, "w0.4_6.0", "first", D2)
bucket_table("S2 0.4 h2, guard first, days 1..7", S2, 0.4, "h2", "first", ALLD)

# ---- skip-contested: creator history (causal: launches >= 15 s earlier) of P(land) under M1 ----
order = sorted(S, key=lambda m: INFO[m]["bt"])
hist = collections.defaultdict(list); rate = {}; pend = collections.deque()
for m in order:
    bt = INFO[m]["bt"]
    while pend and pend[0][0] <= bt - 15:
        _, c, v = pend.popleft(); hist[c].append(v)
    h = hist[INFO[m]["creator"]]; rate[m] = (np.mean(h), len(h)) if h else (np.nan, 0)
    zi = zi_of(m, 0.4); pend.append((bt, INFO[m]["creator"], float(S[m][4][1, 0, zi])))
y = np.array([S[m][4][1, 0, zi_of(m, 0.4)] < 0.5 for m in S2]); x = np.array([rate[m][0] for m in S2]); ok = np.isfinite(x)
def auc(y, s):
    o = np.argsort(s); r = np.empty(len(s)); r[o] = np.arange(1, len(s) + 1); n1 = y.sum(); n0 = len(y) - n1
    return (r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)
pr(f"\n## Skip-contested (creator's earlier launches' mean P(land) under M1)\nAUC of creator history for 'this launch contested (P(land)<0.5)' on S2 picks: {auc(y[ok], -x[ok]):.3f} (n={ok.sum()})\n" + HDR)
for t in (0.3, 0.5, 0.7):
    keepA = [m for m in AP3 if not (rate[m][1] >= 2 and rate[m][0] < t)]
    keepS = [m for m in S2 if not (rate[m][1] >= 2 and rate[m][0] < t)]
    pr(row(f"APEX-3 0.4 w0.4_6 skip hist P(land)<{t}", keepA, 0.4, "w0.4_6.0", "M1", "first", D2))
    pr(row(f"S2 0.4 h2 skip hist P(land)<{t}", keepS, 0.4, "h2", "M1", "first", ALLD))

# ---- realistic-label watchlist ----
def lab_real(m):
    r = net(m, 0.4, "h2", "M1", "first"); return r[0]
byday = collections.defaultdict(list)
for m in S: byday[INFO[m]["day"]].append(m)
H = collections.defaultdict(list); W = []
for d in range(8):
    W.append({c for c, v in H.items() if len(v) >= 3 and sum(v) > 0 and np.mean(v) > 0.002})
    for m in byday[d]: H[INFO[m]["creator"]].append(lab_real(m))   # realistic expected net incl. costs + reverts
SR = [m for m in base if INFO[m]["day"] >= 1 and INFO[m]["creator"] in W[INFO[m]["day"]]]
pr(f"\n## Watchlist rebuilt from REALISTIC labels (M1 first, 0.4 h2) — sizes 0.4 only for non-APEX picks; list size per day {[len(w) for w in W]}\n" + HDR)
pr(row("S2-real 0.4 h2", SR, 0.4, "h2", "M1", "first", ALLD))
pr(row("S2-real 0.4 h2", SR, 0.4, "h2", "M1", "first", ALLD, 1.0, True))
pr(row("S2-real 0.4 h2", SR, 0.4, "h2", "M1", "first", HOLD))
