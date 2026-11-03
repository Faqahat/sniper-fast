#!/usr/bin/env python3
"""STATE step 5 (family A2, added after family A's top 5 failed on r37 because they re-learned QUIET's own signals on QUIET-off runs):
T2 arm-time skip rules ON TOP of the current config. PICK universe = the earlier runs' live T2 windows that the CURRENT config would arm
(QUIET all-4: since_last >= 1 & coh_hold == 0 & wh_fol24 < 4.0 -> skip; min age 2), valued at the current 5:2 stop (QUIET4's values:
measured outcome + stop gain; ops/strategies/presend/filter/quiet4/q6data.py, read-only import). TEST = r37 live (ran this config).
Same search, criteria, K = 5 as PREREG family A. Also writes the per-run table (20 live runs + AMS r28-r33, r38) and the PAPER check."""
import sys, pickle, json, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/prevent/state")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filter/quiet4")
import x4_score as X
import q6data as Q6
D = X.D


def main():
    R = pickle.load(open(f"{D}/windows.pkl", "rb")); F = pickle.load(open(f"{D}/feats.pkl", "rb"))
    allrows = X.build_t2(R, F)
    qrows, _ = Q6.build(); qrows = Q6.values(qrows)
    cur = {}
    for q in qrows:
        if q["src"] != "e" or q["kind"] != "armed": continue
        k = q["key"]; run = k[-3:] + k[1:-3]          # r21FRA -> FRA21
        skip = (q["since"] >= 1) and (q["coh"] == 0) and (q["wf24"] < 4.0)
        arm = ((q["age"] if q["age"] is not None else 99) >= 2) and not skip
        cur[(run, q["mint"], q["slot"])] = (arm, q["val"][(5, 2)])
    P_rows = []; nm = 0; na = 0
    for r in allrows:
        if r["kind"] != "t2" or r["run"] not in X.PICK: continue
        c = cur.get((r["run"], r["x"]["mint"], r["x"]["slot"]))
        if c is None: nm += 1; continue
        if not c[0]: na += 1; continue
        r2 = dict(r); r2["v"] = c[1]; r2["filled"] = r["filled"] and abs(c[1] - r["v"]) < 1e-9 or (r["filled"] and c[1] != -0.0 and c[1] < 0 and r["v"] < 0) or (r["filled"] and c[1] > 0)
        P_rows.append(r2)
    print("A2 PICK windows", len(P_rows), "(unmatched", nm, "skipped by current QUIET/age", na, ") value %+.3f" % sum(r["v"] for r in P_rows), flush=True)
    P = X.Set(P_rows)
    T2 = [r for r in allrows if r["kind"] == "t2"]
    T = X.Set([r for r in T2 if r["run"] == X.TEST]); X38 = [r for r in allrows if r["run"] == X.R38]
    PT = X.Set(P.rows + T.rows)
    feats = sorted(set(k for r in P.rows for k in r["f"]))
    chosen, ntried, npass = X.search_skip(P, feats, "A2 T2 skip on top of current QUIET")
    sh = X.shadow_rows(R, F)
    out = {"tried": ntried, "pass_pick": npass, "pick_windows": len(P.rows), "pick_fills": int(P.filled.sum()), "rules": []}
    L = []
    for ru, sc, lose, win, share in chosen:
        mT = X.mask_of(T.rows, ru); gT, lT, wT = X.skip_gain(T, mT); scT = T.score(gT)
        mPT = X.mask_of(PT.rows, ru); gPT, lPT, wPT = X.skip_gain(PT, mPT); scPT = PT.score(gPT)
        m38 = X.mask_of(X38, ru)
        g38 = sum(-r["v"] for r, m in zip(X38, m38) if m and r["kind"] == "t2")
        six = {lab: bool(m) for (r, m) in zip(X38, m38) for (rk, w), lab in X.SIX.items() if r["w"] == w and r["kind"] == "t2"}
        verdict = "PASS" if (scT["save"] > X.EPS and scPT["ci"][0] > X.EPS and scPT["wo1"] > X.EPS and sc["help"] > sc["hurt"] and lPT > wPT) else ("LEAD" if scT["save"] > X.EPS else "FAIL")
        pap = X.paper_check(sh, ru)
        # per-run: all live runs (raw live windows, no QUIET re-gating; MEASURED), r38 T2
        per = {}
        for rk in X.LIVE20 + ["AMS28", "AMS29", "AMS30", "AMS31", "AMS32", "AMS33"]:
            rr = [r for r in T2 if r["run"] == rk]
            if not rr: continue
            m = X.mask_of(rr, ru)
            per[rk] = dict(save=round(float(sum(-r["v"] for r, k in zip(rr, m) if k)), 4), skipped=int(m.sum()), of=len(rr),
                           fills_skipped=int(sum(1 for r, k in zip(rr, m) if k and r["filled"])))
        d = dict(rule=ru, verdict=verdict, pick=sc, pick_share=share, pick_lose=lose, pick_win=win, test=scT, test_share=float(mT.mean()), test_lose=lT, test_win=wT,
                 pooled=scPT, pooled_lose=lPT, pooled_win=wPT, r38_t2=g38, six=six, paper=pap, per_run_live_raw=per)
        out["rules"].append(d)
        L.append(f"A2 {ru} -> {verdict}\n  PICK {X.fmt(sc)} skip {share:.1%} lose {lose:.2f} win {win:.2f}\n  TEST r37 {X.fmt(scT)} skip {mT.mean():.1%} lose {lT:.2f} win {wT:.2f}\n"
                 f"  POOLED {X.fmt(scPT)} lose {lPT:.2f} win {wPT:.2f}\n  r38 T2 {g38:+.3f}; six {six}\n  paper {pap}\n  per-run raw live {per}")
    json.dump(out, open(f"{D}/RESULTS_A2.json", "w"), indent=1, default=str)
    open(f"{D}/RESULTS_A2.txt", "w").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
