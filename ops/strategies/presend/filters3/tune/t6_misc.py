#!/usr/bin/env python3
"""TUNE t6: (1) lift of each LOG rule vs the period's average trade (flagged mean vs unflagged mean, mSOL/trade); (2) the planned log-only
rules QUIET3-A and G3 on the same segments (incl. the attack); (3) post-trigger holders at landing (a >= 2% holder, not the whale, whose
first buy came after the trigger: age < slots after trigger) as a candidate."""
import sys, pickle
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/filters3/tune")
import tlib as T
P = pickle.load(open("/home/it/sniper-data/filters3/tune/pos_all.pkl", "rb"))
A0, A1 = 1793590164e9 - 60e9, 1793590555e9 + 60e9
for r in P:
    r["attk"] = r["run"] == "r42" and A0 <= r["t"] <= A1
    sat = r["sat"] or 0
    r["post_n"] = sum(1 for h in r["fann"].get("holders", []) if h.get("w") != r["whale"] and (h.get("age") or 0) < sat)
    r["post_pct"] = sum(h.get("pct", 0) for h in r["fann"].get("holders", []) if h.get("w") != r["whale"] and (h.get("age") or 0) < sat)
SEG = {"DEV": lambda r: r["per"] == "DEV" and r["run"] in ("r40", "r41", "r42"), "VALx": lambda r: r["per"] == "VAL" and not r["attk"],
       "ATT": lambda r: r["attk"], "HOLD": lambda r: r["per"] == "HOLD"}
RULES = {"safe": lambda r: r["st"], "group": lambda r: r["grp"], "hclock": lambda r: r["hc"], "guard": lambda r: r["guard"], "ctx85": lambda r: r["ctx85"],
         "holder family (any of 4)": lambda r: r["st"] or r["grp"] or r["hc"] or r["guard"],
         "QUIET3-A (T2 n120<=15 & whd<=3)": lambda r: r["kind"] == "t2" and r["v2"] and r["v2"].get("n_120s", 99) <= 15 and r["quiet"].get("wh_dumps", 99) <= 3 and r["quiet"].get("rule_on") is not False,
         "G3 (fresh<=1 hold sum>=35% at landing)": lambda r: r["fresh_sum"] >= 35,
         "post-trigger >=2% holder at landing": lambda r: r["post_n"] >= 1, "post-trigger holders >= 10%": lambda r: r["post_pct"] >= 10}
print("rule: per segment  n flagged, flagged mean mSOL vs unflagged mean mSOL (lift = unflagged - flagged), net saved")
for rn, rf in RULES.items():
    s = f"{rn:40s}"
    for sn, sf in SEG.items():
        R = [r for r in P if sf(r)]; F = [r["pnl"] for r in R if rf(r)]; U = [r["pnl"] for r in R if not rf(r)]
        fm = 1000 * sum(F) / len(F) if F else 0; um = 1000 * sum(U) / len(U) if U else 0
        s += f" | {sn} {len(F):3d} {fm:+6.1f} vs {um:+5.1f} save {-sum(F):+6.3f} w5 {T.wo_top(F):+6.3f}"
    print(s)
