#!/usr/bin/env python3
"""TUNE t2: for each LOG rule, winners it marks vs losers it marks: feature medians (DEV and VAL ex-attack) with the time each feature is
known (ARM / SIGN / LAND / OUTCOME = after the fact, for understanding only)."""
import sys, pickle, statistics as st
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/tune")
import tlib as T
P = pickle.load(open("/home/moiz/sniper-data/filters3/tune/pos_all.pkl", "rb"))
A0, A1 = 1793590104e9 - 60e9, 1793590555e9 + 60e9      # template attack span from t1 (08:29:24..08:35:55) +- 60 s
for r in P: r["attk"] = r["run"] == "r42" and A0 <= r["t"] <= A1
FE = [("ARM", "kind", lambda r: 1.0 if r["kind"] == "t2" else 0.0), ("ARM", "trig_pct", lambda r: r["trig"].get("pct") or r["dump"].get("pct") or 0),
      ("ARM", "age_slots", lambda r: r["trig"].get("age_slots") if r["kind"] == "t2" else r["dump"].get("age_slots")),
      ("ARM", "vsol", lambda r: (r["trig"].get("vsol") or r["dump"].get("vsol") or 0) / 1e9),
      ("ARM", "n_120s", lambda r: r["v2"].get("n_120s")), ("ARM", "wh_dumps", lambda r: r["quiet"].get("wh_dumps")),
      ("ARM", "nb50", lambda r: r["ann"].get("nb50")), ("ARM", "cr_pct", lambda r: r["ann"].get("cr_pct")),
      ("SIGN", "ob6", lambda r: r["ob6"]), ("LAND", "sat", lambda r: r["sat"]), ("LAND", "depth", lambda r: r["depth"]),
      ("LAND", "risky_sum", lambda r: r["risky_sum"]), ("LAND", "risky_max", lambda r: r["risky_max"]), ("LAND", "risky_n", lambda r: r["risky_n"]),
      ("LAND", "risky_maxhz", lambda r: r["risky_maxhz"]), ("LAND", "risky_minage", lambda r: r["risky_minage"]), ("LAND", "risky_maxn", lambda r: r["risky_maxn"]),
      ("LAND", "st_pct", lambda r: r["st_pct"]), ("LAND", "st_age", lambda r: r["st_age"]), ("LAND", "hc_pct", lambda r: r["hc_pct"]), ("LAND", "hc_age", lambda r: r["hc_age"]),
      ("LAND", "fresh_sum", lambda r: r["fresh_sum"]), ("LAND", "oth_max", lambda r: r["oth_max"]), ("LAND", "oth_sum", lambda r: r["oth_sum"]),
      ("LAND", "guard_pct", lambda r: r["guard_pct"]), ("SIGN", "guard_sign", lambda r: r["guard_sign"]),
      ("OUT", "followed", lambda r: 1.0 if r["followed"] else 0.0), ("OUT", "sold_in_hold", lambda r: r["sold_in_hold"]), ("OUT", "whale_sold", lambda r: r["whale_sold_in_hold"])]
RULES = {"safe": lambda r: r["st"], "group": lambda r: r["grp"], "hclock": lambda r: r["hc"], "guard": lambda r: r["guard"], "ctx85": lambda r: r["ctx85"],
         "gcr": lambda r: r["gcr"], "ALL": lambda r: True}
def med(v):
    v = [x for x in v if x is not None]
    return st.median(v) if v else float("nan")
for per, sel in (("DEV(r40+)", lambda r: r["per"] == "DEV" and r["run"] in ("r40", "r41", "r42")), ("VALx", lambda r: r["per"] == "VAL" and not r["attk"]),
                 ("HOLD", lambda r: r["per"] == "HOLD")):
    print(f"\n==== {per}")
    print(f"{'rule':7s} {'W/L':5s} {'n':>4s} {'sol':>7s} " + " ".join(f"{n[:9]:>9s}" for _, n, _ in FE))
    for rn, rf in RULES.items():
        R = [r for r in P if sel(r) and rf(r)]
        for lab, g in (("win", [r for r in R if r["pnl"] > 0]), ("lose", [r for r in R if r["pnl"] <= 0])):
            print(f"{rn:7s} {lab:5s} {len(g):4d} {sum(r['pnl'] for r in g):+7.3f} " + " ".join(f"{med([f(r) for r in g]):9.2f}" for _, _, f in FE))
