#!/usr/bin/env python3
"""VERIFY v2a (MEASURED, read-only): how our LIVE pre-send tries land relative to a price-crossing drop, unconditional on fill.
For every landed pre-send try T (presend_attempt_land, res ok / 6042) of the given runs:
  * the tape state just before T's landing position -> spot price; predicted fill = spot <= T's lim (check of the price rule);
  * if the spot crossed below T's lim since T's send slot (a trade X by another wallet, price before X > lim >= price after X,
    X after the start of T's send slot): X = the crossing, G = cc(T) - cc(X) ms, k = outside trades strictly between X and T.
    'first' = T is the first of our landed tries after X.
Out: DATA/v2a_<tag>.pkl rows (run, mint, slot, idx, res, lim, p_before, pred, G, k, first) + printed summary.
usage: v2a_live_gap.py TAB TAG RUNFILE [RUNFILE ...]"""
import sys, pickle, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/verify")
import vlib as V

DATA = "/home/moiz/sniper-data/haqq_dissect/verify"

if __name__ == "__main__":
    tab, tag = sys.argv[1], sys.argv[2]; files = sys.argv[3:]
    R = V.load_runs(files)
    tries = [r for r in R if r.get("ev") == "presend_attempt_land" and r.get("res") in ("ok", "6042") and r.get("slot") and r.get("idx") is not None]
    mints = {r["mint"] for r in tries}
    tp = V.Tape(tab, mints)
    S0, S1 = tp.s0, tp.s0 + len(tp.bsz)
    by = collections.defaultdict(list)
    for r in tries:
        if S0 + 50 <= r["slot"] < S1: by[r["mint"]].append(r)
    out = []
    for mint, ts in by.items():
        X = tp.rows(mint)
        if X is None or len(X) == 0: continue
        pos = list(zip(X["slot"].tolist(), X["idx"].tolist(), X["j"].tolist()))
        price = (X["vsol"] / np.maximum(X["vtok"], 1)).astype(float)
        ours = np.isin(X["signer"], list(tp.our)) | np.isin(X["user"], list(tp.our))
        ts.sort(key=lambda r: (r["slot"], r["idx"]))
        land_pos = [(r["slot"], r["idx"]) for r in ts]
        import bisect
        for q, r in enumerate(ts):
            kb = bisect.bisect_left(pos, (r["slot"], r["idx"], -1)) - 1
            if kb < 0: continue
            pb = price[kb]; lim = r["lim"]; pred = pb <= lim
            ss = r.get("send_slot") or r["slot"]
            # crossing: the last outside trade X <= kb with price_before(X) > lim >= price_after(X), X at/after the send slot start
            G = k = None; first = None
            # crossing: the FIRST trade X in [start of slot ss-1 .. kb] with price_before(X) > lim >= price_after(X) (unconditional on
            # the price still being <= lim at T: a 6042 after a crossing = others bought it back above our limit first)
            a0 = bisect.bisect_left(pos, (ss - 1, -1, -1))
            cx = None
            for x in range(max(a0, 1), kb + 1):
                if price[x] <= lim and price[x - 1] > lim and not ours[x]:
                    cx = x; break
            if cx is not None:
                G = tp.cc(int(r["slot"]), int(r["idx"])) - tp.cc(int(X["slot"][cx]), int(X["idx"][cx]))
                k = int((~ours[cx + 1:kb + 1]).sum())
                prev = [p for p in land_pos[:q] if p > (int(X["slot"][cx]), int(X["idx"][cx]))]
                first = len(prev) == 0
            out.append(dict(run=r["_run"], mint=mint, slot=r["slot"], idx=r["idx"], res=r["res"], lim=lim, pb=float(pb), pred=bool(pred), G=G, k=k, first=first,
                            cx_own=None))
    pickle.dump(out, open(f"{DATA}/v2a_{tag}.pkl", "wb"))
    n = len(out); ok = sum(r["res"] == "ok" for r in out)
    tp_ = sum(r["pred"] and r["res"] == "ok" for r in out); fp = sum(r["pred"] and r["res"] != "ok" for r in out)
    fn = sum((not r["pred"]) and r["res"] == "ok" for r in out)
    print(f"{tag}: landed tries {n:,}, live fills {ok}; price rule: both fill {tp_}, rule fill/live 6042 {fp}, rule 6042/live fill {fn}")
    C = [r for r in out if r["G"] is not None and r["first"]]
    print(f"first try after a crossing: {len(C)}; live filled {sum(r['res'] == 'ok' for r in C)}")
    if C:
        G = np.array([r["G"] for r in C]); K = np.array([r["k"] for r in C])
        print(f"  G ms pctl 10/25/50/75/90: {np.percentile(G, [10, 25, 50, 75, 90]).round(1)}; k=0 share {np.mean(K == 0):.3f}; k dist " +
              " ".join(f"{v}:{np.mean(K == v):.3f}" for v in range(5)) + f" 5+:{np.mean(K >= 5):.3f}")
        for lo, hi in ((0, 0), (1, 1), (2, 3), (4, 7), (8, 999)):
            m = (K >= lo) & (K <= hi)
            if m.sum(): print(f"  k {lo}-{hi}: n {m.sum()}, live fill {np.mean([C[i]['res'] == 'ok' for i in np.flatnonzero(m)]):.3f}")
    F = [r for r in out if r["res"] == "ok" and r["G"] is not None]
    if F:
        G = np.array([r["G"] for r in F]); K = np.array([r["k"] for r in F])
        print(f"live FILLS with a crossing: {len(F)}; G median {np.median(G):.1f} ms; k=0 {np.mean(K == 0):.3f}")
