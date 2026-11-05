#!/usr/bin/env python3
"""TUNE t3: LOG rules (real fills): each rule as logged, then one-at-a-time refinements (AND a condition) and AND-of-two-rules,
scored per period. FIT = DEV (r37..r41 + r42 to 11-01 12:00 PKT, only runs that log the rule's inputs); CHECK 1 = VAL ex attack and
VAL incl attack; CHECK 2 = HOLD (r43..r46). Pass = better precision (losers / marked) AND more net saved than the base rule in DEV,
VALx, VAL, HOLD, and more net w/o its top 5 in each. Times: ARM / SIGN / LAND as labelled."""
import sys, pickle, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/tune")
import tlib as T
P = pickle.load(open("/home/moiz/sniper-data/filters3/tune/pos_all.pkl", "rb"))
A0, A1 = 1793590164e9 - 60e9, 1793590555e9 + 60e9
for r in P: r["attk"] = r["run"] == "r42" and A0 <= r["t"] <= A1
RUNH = {"r37": 18.37, "r38": 1.63, "r39": 3.14, "r40": 17.29, "r41": 1.32, "r42D": 32.12, "VAL": 20.6, "HOLD": 14.23}
NEED = {"ann": {"r39", "r40", "r41", "r42"} , "risk": {"r40", "r41", "r42"}, "guard": {"r41", "r42"}}
def dev_hours(need):
    runs = NEED[need]
    return sum(RUNH[x] for x in runs if x != "r42") + (RUNH["r42D"] if "r42" in runs else 0)
SEGS = {"DEV": lambda r: r["per"] == "DEV", "VALx": lambda r: r["per"] == "VAL" and not r["attk"], "VAL": lambda r: r["per"] == "VAL",
        "ATT": lambda r: r["attk"], "HOLD": lambda r: r["per"] == "HOLD"}
def score(pred, need):
    out = {}
    for sn, sf in SEGS.items():
        R = [r for r in P if sf(r) and (sn != "DEV" or r["run"] in NEED[need])]
        v = [r["pnl"] for r in R if pred(r)]
        s = T.summ(v); s["wo5"] = T.wo_top(v)
        h = dev_hours(need) if sn == "DEV" else (RUNH["VAL"] - (0.67 if sn == "VALx" else 0) if sn in ("VAL", "VALx") else RUNH["HOLD"] if sn == "HOLD" else 0.67)
        s["day"] = round(s["saved"] / h * 24, 2) if h else None
        s["base_mean"] = round(sum(r["pnl"] for r in R) / len(R), 4) if R else None
        out[sn] = s
    return out
def fmt(name, sc):
    return f"{name:44s}" + "".join(f" | {sn} {s['n']:3d} p{(s['prec'] or 0):.2f} {s['saved']:+6.3f} w5 {s['wo5']:+6.3f}" for sn, s in sc.items() if sn != "ATT") + f" | ATT {sc['ATT']['n']} {sc['ATT']['saved']:+.2f}"
def passes(sc, b):
    ok = True
    for sn in ("DEV", "VALx", "VAL", "HOLD"):
        s, bb = sc[sn], b[sn]
        if s["n"] == 0: return False
        ok &= (s["prec"] or 0) > (bb["prec"] or 0) and s["saved"] > bb["saved"] and s["wo5"] > bb["wo5"]
    return ok
def GR(each=2, risk=5, hz=0.3, sm=6.0, age=None, nmin=0, nmax=None):
    def f(r):
        hs = [h for h in r["fann"].get("holders", []) if h.get("pct", 0) >= each and (h.get("risk") or 0) >= risk and (h.get("hz3") or 0) >= hz
              and (age is None or (h.get("age") or 0) <= age) and (h.get("n") or 0) >= nmin and (nmax is None or (h.get("n") or 0) <= nmax)]
        return sum(h["pct"] for h in hs) >= sm
    return f
BASE = {"safe sell timer": (lambda r: r["st"], "risk"), "group risk": (lambda r: r["grp"], "risk"), "holder clock": (lambda r: r["hc"], "risk"),
        "landing guard": (lambda r: r["guard"], "guard"), "ctx85": (lambda r: r["ctx85"], "ann"), "bad creator (run)": (lambda r: r["gcr"], "ann")}
CTX = {"T2 only [ARM]": lambda r: r["kind"] == "t2", "re-arm only [ARM]": lambda r: r["kind"] == "rearm",
       "dip < 15% [LAND]": lambda r: r["depth"] < 0.15, "dip >= 15% [LAND]": lambda r: r["depth"] >= 0.15,
       "n_120s <= 15 [ARM,T2]": lambda r: (r["v2"].get("n_120s") if r["v2"] else 99) <= 15, "n_120s > 15 [ARM,T2]": lambda r: (r["v2"].get("n_120s") if r["v2"] else 0) > 15,
       "nb50 <= 6 [ARM]": lambda r: (r["ann"].get("nb50") or 0) <= 6, "nb50 > 6 [ARM]": lambda r: (r["ann"].get("nb50") or 0) > 6,
       "wh_dumps <= 3 [ARM,T2]": lambda r: r["kind"] == "t2" and (r["quiet"].get("wh_dumps") or 0) <= 3, "wh_dumps > 3 [ARM,T2]": lambda r: r["kind"] == "t2" and (r["quiet"].get("wh_dumps") or 0) > 3,
       "trigger >= 8% [ARM]": lambda r: (r["trig"].get("pct") or r["dump"].get("pct") or 0) >= 8, "trigger < 8% [ARM]": lambda r: (r["trig"].get("pct") or r["dump"].get("pct") or 0) < 8,
       "token age <= 20 [ARM]": lambda r: ((r["trig"].get("age_slots") if r["kind"] == "t2" else r["dump"].get("age_slots")) or 0) <= 20,
       "token age > 20 [ARM]": lambda r: ((r["trig"].get("age_slots") if r["kind"] == "t2" else r["dump"].get("age_slots")) or 0) > 20,
       "ob6 >= 6 [SIGN]": lambda r: r["ob6"] >= 6, "ob6 < 6 [SIGN]": lambda r: r["ob6"] < 6,
       "creator holds >= 3% [ARM]": lambda r: (r["ann"].get("cr_pct") or 0) >= 3, "creator holds < 3% [ARM]": lambda r: (r["ann"].get("cr_pct") or 0) < 3,
       "fill <= 3 slots after trig [LAND]": lambda r: (r["sat"] or 0) <= 3, "fill > 3 slots after trig [LAND]": lambda r: (r["sat"] or 0) > 3,
       "risky holder age <= 10 [LAND]": lambda r: r["risky_minage"] <= 10, "risky holder age > 10 [LAND]": lambda r: r["risky_minage"] > 10 and r["risky_n"] > 0,
       "risky holder n >= 16 [LAND]": lambda r: r["risky_maxn"] >= 16, "risky max hz3 >= 0.5 [LAND]": lambda r: r["risky_maxhz"] >= 0.5,
       "risky sum >= 10 [LAND]": lambda r: r["risky_sum"] >= 10, "risky max >= 6 [LAND]": lambda r: r["risky_max"] >= 6,
       "fresh holders >= 20% [LAND]": lambda r: r["fresh_sum"] >= 20, "other max >= 12 [LAND]": lambda r: r["oth_max"] >= 12,
       "+safe": lambda r: r["st"], "+group": lambda r: r["grp"], "+hclock": lambda r: r["hc"], "+guard": lambda r: r["guard"], "+ctx85": lambda r: r["ctx85"], "+gcr": lambda r: r["gcr"]}
res = {}
print("LOG RULES: base, then base AND condition. Columns: n marked, precision (losers/marked), net saved, w/o top 5. PASS = beats base everywhere")
for bn, (bf, need) in BASE.items():
    b = score(bf, need); res[bn] = {"base": b, "ref": {}}
    print(f"\n### {bn} (DEV runs {sorted(NEED[need])}; DEV {dev_hours(need):.1f} h)")
    print(fmt("BASE", b))
    for cn, cf in CTX.items():
        sc = score((lambda bf, cf: lambda r: bf(r) and cf(r))(bf, cf), need)
        ok = passes(sc, b); res[bn]["ref"][cn] = dict(sc, PASS=ok)
        print(fmt(("PASS " if ok else "     ") + cn, sc))
# generalized holder rule grid (fit DEV, check later)
print("\n### generalized holder rule GR(each%, holds at risk, hz3, sum%, max holder age, min holds) vs group risk; top 15 by DEV net, and every PASS")
gb = res["group risk"]["base"]; grid = []
for each in (2, 4, 6):
    for risk in (5, 10):
        for hz in (0.3, 0.5, 0.7):
            for sm in (6, 10, 15):
                for age in (None, 20, 8):
                    for nmin in (0, 16):
                        sc = score(GR(each, risk, hz, sm, age, nmin), "risk")
                        grid.append(((each, risk, hz, sm, age, nmin), sc, passes(sc, gb)))
grid.sort(key=lambda x: -x[1]["DEV"]["saved"])
for p, sc, ok in grid[:15]: print(fmt(("PASS " if ok else "     ") + "GR" + str(p), sc))
npass = [g for g in grid if g[2]]
print(f"grid {len(grid)} combos, PASS {len(npass)}")
for p, sc, ok in npass: print(fmt("PASS GR" + str(p), sc))
res["GR_grid"] = [{"p": list(map(str, p)), "sc": sc, "PASS": ok} for p, sc, ok in grid]
json.dump(res, open("/home/moiz/sniper-data/filters3/tune/t3_scan.json", "w"))
