#!/usr/bin/env python3
"""STATE step 6: per-run tables for the A2 survivors (current-config universe on PICK runs, live r37, live r38) and the r38 six-loss state table."""
import sys, pickle, json, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/prevent/state"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filter/quiet4")
import x4_score as X, q6data as Q6
D = X.D
R = pickle.load(open(f"{D}/windows.pkl", "rb")); F = pickle.load(open(f"{D}/feats.pkl", "rb"))
allrows = X.build_t2(R, F)
qrows, _ = Q6.build(); qrows = Q6.values(qrows); cur = {}
for q in qrows:
    if q["src"] != "e" or q["kind"] != "armed": continue
    k = q["key"]; run = k[-3:] + k[1:-3]
    skip = (q["since"] >= 1) and (q["coh"] == 0) and (q["wf24"] < 4.0)
    cur[(run, q["mint"], q["slot"])] = (((q["age"] if q["age"] is not None else 99) >= 2) and not skip, q["val"][(5, 2)])
RULES = [[("nbuyers50", "<=", 1.0)], [("nbuyers50", "<=", 1.0), ("since_last", ">=", 7.0)], [("bsol50", "<=", 2.949629629)]]
out = {"per_run": {}, "six": {}}
order = X.LIVE20[:-2] + ["AMS28", "AMS29", "AMS30", "AMS31", "AMS32", "AMS33", "AMS37", "AMS38"]
for ru in RULES:
    name = " & ".join(f"{a}{b}{c:g}" for a, b, c in ru); tab = {}
    print("RULE", name)
    print(f"{'run':7s} {'hours':>5s} {'windows':>7s} {'fills':>5s} {'value':>7s} | {'skip':>4s} {'skipF':>5s} {'saved':>7s} {'saved/day':>9s}  src")
    for rk in order:
        rr = [r for r in allrows if r["run"] == rk and r["kind"] == "t2"]
        src = "live (ran current QUIET)" if rk in ("AMS37", "AMS38") else "live, current-config subset (QUIET4 values)"
        if rk not in ("AMS37", "AMS38"):
            r2 = []
            for r in rr:
                c = cur.get((rk, r["x"]["mint"], r["x"]["slot"]))
                if c is None or not c[0]: continue
                z = dict(r); z["v"] = c[1]; r2.append(z)
            rr = r2
        m = X.mask_of(rr, ru) if rr else np.zeros(0, bool)
        sv = float(sum(-r["v"] for r, k in zip(rr, m) if k)); h = R[rk]["hours"]
        d = dict(hours=round(h, 2), windows=len(rr), fills=sum(1 for r in rr if r["filled"]), value=round(sum(r["v"] for r in rr), 3), skipped=int(m.sum()),
                 skipped_fills=int(sum(1 for r, k in zip(rr, m) if k and r["filled"])), saved=round(sv, 3), saved_per_day=round(sv * 24 / h, 2) if h > 0 else None, src=src)
        tab[rk] = d
        print(f"{rk:7s} {h:5.1f} {d['windows']:7d} {d['fills']:5d} {d['value']:+7.3f} | {d['skipped']:4d} {d['skipped_fills']:5d} {sv:+7.3f} {d['saved_per_day'] or 0:+9.2f}  {src}")
    out["per_run"][name] = tab
# six-loss state
KEYS = ["age", "pct", "wsol", "vsol", "top1", "top10", "oth_n6", "oth_sum3", "who_pct", "who_ret", "nbuyers50", "nb5", "ns5", "ssol5", "ndump3", "lc_pct", "cre_pct", "ovh50", "hret"]
print("\nSIX r38 losses: arm-time state (re-arm: dumper = who) and fill-time (descriptive)")
for (rk, w), lab in X.SIX.items():
    r = next((r for r in allrows if r["run"] == rk and r["w"] == w), None)
    if r is None: print(lab, "no features"); continue
    f = r["f"]; raw = r["raw"]
    s = {k: (round(f[k], 2) if isinstance(f.get(k), float) else f.get(k)) for k in KEYS}
    s.update(fill_prev_left=round(raw.get("fill_prev_left", -1), 2), fill_prev_is_who=raw.get("fill_prev_is_who"), hold_sell_sol=round(raw.get("hold_sell_sol", 0), 2),
             hold_max_sell=round(raw.get("hold_max_sell", 0), 2), ev={k: v - r["x"]["slot"] for k, v in r["ev"].items()} if r["kind"] == "t2" else None, v=round(r["v"], 4))
    out["six"][lab] = s
    print(lab, s)
json.dump(out, open(f"{D}/TABLES.json", "w"), indent=1)
