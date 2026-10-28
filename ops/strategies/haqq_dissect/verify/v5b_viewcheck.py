#!/usr/bin/env python3
"""VERIFY v5b (MEASURED): is my stale-view rule (a try's limit = 0.88 x price at L - s2rx) right? For every live landed pre-send try
of the given runs on the tape: model lim vs the live lim; and model fill vs live result. usage: v5b_viewcheck.py TAB RUN..."""
import sys, collections, bisect
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/verify")
import vlib as V
tab = sys.argv[1]; R = V.load_runs(sys.argv[2:])
tries = [r for r in R if r.get("ev") == "presend_attempt_land" and r.get("res") in ("ok", "6042") and r.get("slot") and r.get("idx") is not None]
tp = V.Tape(tab, {r["mint"] for r in tries})
S0, S1 = tp.s0 + 50, tp.s0 + len(tp.bsz)
by = collections.defaultdict(list)
for r in tries:
    if S0 <= r["slot"] < S1: by[r["mint"]].append(r)
cmp = collections.Counter(); ratio = []; extra = []
for mint, ts in by.items():
    X = tp.rows(mint)
    if X is None: continue
    ours = np.isin(X["signer"], list(tp.our)) | np.isin(X["user"], list(tp.our)); X = X[~ours]
    if not len(X): continue
    cc = np.array([tp.cc(int(a), int(b)) for a, b in zip(X["slot"], X["idx"])]); price = X["vsol"] / np.maximum(X["vtok"], 1)
    for r in ts:
        s2 = r.get("ms_send_to_first_rx") or r.get("ms_send_to_rx")
        if s2 is None: continue
        L = tp.cc(int(r["slot"]), int(r["idx"]))
        kb = int(np.searchsorted(cc, L, side="left")) - 1; kv = int(np.searchsorted(cc, L - s2, side="right")) - 1
        if kb < 0 or kv < 0: continue
        mlim = 0.88 * price[kv]; llim = r["lim"]
        ratio.append(mlim / llim)
        mf = price[kb] <= mlim; lf = r["res"] == "ok"
        cmp[(mf, lf)] += 1
rt = np.array(ratio)
print(f"tries {len(rt):,}: model lim / live lim pctl 5/25/50/75/95 {np.percentile(rt, [5, 25, 50, 75, 95]).round(4)}; share model lim > live lim by >1%: {np.mean(rt > 1.01):.3f}; < -1%: {np.mean(rt < 0.99):.3f}")
print("model fill / live fill: " + ", ".join(f"model {a} live {b}: {n}" for (a, b), n in sorted(cmp.items())))
