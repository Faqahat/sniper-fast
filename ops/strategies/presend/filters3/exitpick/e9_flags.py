#!/usr/bin/env python3
"""EXITPICK step 9 (owner 11-03 23:00): log-only risk flags at landing as an EXIT input: 'flagged -> sell sooner' vs the normal t125.
Short exits: first chance (fill seen + 1 ms, clock), 50 / 75 ms (own delay), t100 (own delay), s1. Also 'flagged -> longer' (t1000) for symmetry.
Choice on DEV (best flag-set x exit), shown on VAL and HOLD (r45-r50) and on the coordinator's HOLD r43-r50."""
import json
from elib import *
R = load(); A = json.load(open(f"{O}/alt.json"))
for r in R: r["alt"] = A[r["sig"]]
def pnl(r, ex, var="y"):
    fc = "_fc" if var == "y_fc" else ""
    if ex == "first": v = r["alt"]["clock1" + fc]
    elif ex in ("own50", "own75"): v = r["alt"][ex + fc]
    else: return y(r, ex, var)
    return v if v is not None else y(r, "t125", var)
FL = {"st (safe sell timer)": lambda r: r["A"]["fl_st"] > 0, "grp (group risk)": lambda r: r["A"]["fl_grp"] > 0, "clock (holder clock)": lambda r: r["A"]["fl_clock"] > 0,
      "ctx85": lambda r: r["A"]["fl_ctx85"] > 0, "guard (landing)": lambda r: r["A"]["fl_guard"] > 0,
      ">=1 flag": lambda r: r["A"]["fl_n"] >= 1, ">=2 flags": lambda r: r["A"]["fl_n"] >= 2, ">=3 flags": lambda r: r["A"]["fl_n"] >= 3}
EXS = ["first", "own50", "own75", "t100", "s1", "t1000"]
groups = {"DEV": lambda r: r["split"] == "dev", "VAL": lambda r: r["split"] == "val", "HOLD r45-50": lambda r: r["split"] == "hold",
          "HOLD r43-50": lambda r: r["run"] >= 43}
def g(rows, fl, ex, var="y"):
    sel = [r for r in rows if FL[fl](r)]
    d = [pnl(r, ex, var) - y(r, "t125", var) for r in sel]
    s = sorted(d)
    return sum(d), sum(s[:-5]) if len(s) > 5 else 0.0, len(sel), d
print("gain vs t125 of 'flagged -> exit X' (SOL; w/o top5 = without the 5 biggest per-trade gains; fc = followers -20%)")
best = None
for fl in FL:
    for ex in EXS:
        cells = []
        for gn, c in groups.items():
            rows = [r for r in R if c(r)]
            a, a5, n, _ = g(rows, fl, ex); f, _, _, _ = g(rows, fl, ex, "y_fc")
            cells.append(f"{gn} {a:+.3f} (w/o5 {a5:+.3f}, fc {f:+.3f}, n{n})")
            if gn == "DEV" and (best is None or a > best[0]): best = (a, fl, ex)
        print(f"  {fl:<20} -> {ex:<6} | " + " | ".join(cells))
print(f"\nDEV pick: {best[1]} -> {best[2]} (DEV {best[0]:+.3f})")
for gn, c in groups.items():
    rows = [r for r in R if c(r)]
    a, a5, n, d = g(rows, best[1], best[2]); f, f5, _, _ = g(rows, best[1], best[2], "y_fc"); rs = g(rows, best[1], best[2], "y_rs")[0]
    ci = boot_ci(d)
    print(f"  {gn:<12} gain {a:+.3f} CI [{ci[0]:+.2f},{ci[1]:+.2f}] w/o top5 {a5:+.3f} fc20 {f:+.3f} rs {rs:+.3f} | flagged {n}/{len(rows)}")
for run in range(42, 51):
    rows = [r for r in R if r["run"] == run]; a, _, n, _ = g(rows, best[1], best[2])
    print(f"   r{run}: {a:+.3f} on {n}")
