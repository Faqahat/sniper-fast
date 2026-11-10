#!/usr/bin/env python3
"""TUNE t4: LIVE skips (create-slot, age-1, QUIET, lone whale) on the shadow's paper (row c net_cheap scaled to the live size, as the
dashboard; ESTIMATE). Per period and per run; then subgroups at ARM time that a skip could RELEASE (paper of the released triggers must be
> 0 in DEV, VAL ex attack, VAL, HOLD and w/o its top 5) or that a skip should keep."""
import sys, json, collections, pickle
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/filters3/tune")
import tlib as T
S = T.skips()
pickle.dump(S, open("/home/it/sniper-data/filters3/tune/skips_all.pkl", "wb"))
A0, A1 = 1793590164e9 - 60e9, 1793590555e9 + 60e9
for s in S: s["attk"] = s["run"] == "r42" and A0 <= s["t"] <= A1
H = {"DEV": 74.32, "VALx": 19.93, "VAL": 20.6, "HOLD": 14.23}
SEG = {"DEV": lambda s: s["per"] == "DEV", "VALx": lambda s: s["per"] == "VAL" and not s["attk"], "VAL": lambda s: s["per"] == "VAL", "HOLD": lambda s: s["per"] == "HOLD"}
def sc(ss):
    out = {}
    for sn, sf in SEG.items():
        x = [s for s in ss if sf(s)]; v = [s["paper"] for s in x if s["paper"] is not None]
        d = T.summ(v); d["skipped"] = len(x); d["wo5"] = T.wo_top(v); d["day"] = round(d["saved"] / H[sn] * 24, 2)
        d["paper_sum"] = round(sum(v), 3); d["paper_wo5"] = round(sum(sorted(v, reverse=True)[5:]), 3)   # for a RELEASE: what the released add
        out[sn] = d
    return out
def fmt(name, d, release=False):
    if release:
        return f"{name:46s}" + "".join(f" | {sn} {d[sn]['n']:4d} add {d[sn]['paper_sum']:+6.3f} w/o5 {d[sn]['paper_wo5']:+6.3f}" for sn in SEG)
    return f"{name:46s}" + "".join(f" | {sn} {d[sn]['skipped']:4d}/{d[sn]['n']:3d} p{(d[sn]['prec'] or 0):.2f} {d[sn]['saved']:+6.3f} w5 {d[sn]['wo5']:+6.3f} {d[sn]['day']:+5.2f}/d" for sn in SEG)
res = {}
print("LIVE SKIPS (paper ESTIMATE): skipped/scored, precision, net saved, w/o top 5, SOL/day")
for why in ("create_slot", "young_age", "quiet", "lone_whale", "breaker"):
    ss = [s for s in S if s["why"] == why]
    if not ss: continue
    res[why] = {"all": sc(ss)}
    print(fmt(why, res[why]["all"]))
    print("   per run: " + " ".join(f"{r}:{sum(1 for s in ss if s['run'] == r)}/{-sum(s['paper'] for s in ss if s['run'] == r and s['paper'] is not None):+.2f}" for r in T.RUNS))
    print("   r42 days: " + " ".join(f"{d}:{-sum(s['paper'] for s in ss if s['run'] == 'r42' and s['day'] == d and s['paper'] is not None and not s['attk']):+.2f}" for d in ("10-31", "11-01", "11-02")))
# features at ARM for skipped triggers
def tp(s): return s["trig"].get("pct") or 0
def tsol(s): return (s["trig"].get("sol") or 0) / 1e9
def q(s, k, d=0): v = s["quiet"].get(k); return d if v is None else v
def v2(s, k, d=0): v = s["v2"].get(k); return d if v is None else v
SUB = {"pct 6-8": lambda s: tp(s) < 8, "pct 8-10": lambda s: 8 <= tp(s) < 10, "pct 10-15": lambda s: 10 <= tp(s) < 15, "pct >= 15": lambda s: tp(s) >= 15,
       "sol < 2": lambda s: tsol(s) < 2, "sol 2-4": lambda s: 2 <= tsol(s) < 4, "sol >= 4": lambda s: tsol(s) >= 4,
       "wh_dumps 0": lambda s: q(s, "wh_dumps") == 0, "wh_dumps 1-3": lambda s: 1 <= q(s, "wh_dumps") <= 3, "wh_dumps 4-20": lambda s: 4 <= q(s, "wh_dumps") <= 20,
       "wh_dumps > 20": lambda s: q(s, "wh_dumps") > 20, "wh_fol >= 4": lambda s: q(s, "wh_fol", -1) >= 4, "wh_fol 0-4": lambda s: 0 <= q(s, "wh_fol", -1) < 4,
       "since_last 0": lambda s: q(s, "since_last", 1) == 0, "since_last >= 1": lambda s: q(s, "since_last", 1) >= 1,
       "cohort holds": lambda s: q(s, "coh_hold") > 0, "all4 quiet": lambda s: bool(s["quiet"].get("all4")), "not all4": lambda s: s["quiet"] and not s["quiet"].get("all4"),
       "n_120s <= 5": lambda s: v2(s, "n_120s", 0) <= 5, "n_120s 6-15": lambda s: 6 <= v2(s, "n_120s", 0) <= 15, "n_120s > 15": lambda s: v2(s, "n_120s", 0) > 15,
       "nb50 <= 2": lambda s: (s["ann"].get("nb50") or 0) <= 2, "nb50 3-8": lambda s: 3 <= (s["ann"].get("nb50") or 0) <= 8, "nb50 > 8": lambda s: (s["ann"].get("nb50") or 0) > 8,
       "creator holds >= 3%": lambda s: (s["ann"].get("cr_pct") or 0) >= 3, "creator holds < 3%": lambda s: (s["ann"].get("cr_pct") or 0) < 3,
       "vsol >= 40": lambda s: (s["trig"].get("vsol") or 0) / 1e9 >= 40, "vsol < 40": lambda s: (s["trig"].get("vsol") or 0) / 1e9 < 40}
for why in ("create_slot", "young_age", "quiet", "lone_whale"):
    ss = [s for s in S if s["why"] == why]
    print(f"\n### {why}: subgroups (as a RELEASE: what the released triggers ADD on paper; release passes if add > 0 in all 4 and w/o 5 > 0)")
    res[why]["sub"] = {}
    for sn, sf in SUB.items():
        d = sc([s for s in ss if sf(s)]); ok = all(d[x]["paper_sum"] > 0 and d[x]["paper_wo5"] > 0 for x in SEG) and all(d[x]["n"] >= 3 for x in SEG)
        res[why]["sub"][sn] = dict(d, RELEASE_PASS=ok)
        print(fmt(("PASS " if ok else "     ") + sn, d, release=True))
# winners vs losers of the scored skips (DEV): medians
import statistics as st
def med(v): v = [x for x in v if x is not None]; return round(st.median(v), 2) if v else None
print("\nwinners vs losers among scored skips (medians: pct, sol, wh_dumps, wh_fol, n_120s, nb50, cr_pct, shadow fill slots after trigger, whale sold into fill, n_ahead)")
for why in ("create_slot", "young_age", "quiet"):
    for per in ("DEV", "VAL", "HOLD"):
        for lab, f in (("win", lambda v: v > 0), ("lose", lambda v: v <= 0)):
            g = [s for s in S if s["why"] == why and s["per"] == per and s["paper"] is not None and f(s["paper"])]
            print(f"  {why:11s} {per:4s} {lab:4s} {len(g):4d} {sum(s['paper'] for s in g):+7.3f} | " + " ".join(str(med([fn(s) for s in g])) for fn in (
                tp, tsol, lambda s: q(s, "wh_dumps"), lambda s: q(s, "wh_fol", -1), lambda s: v2(s, "n_120s", None), lambda s: s["ann"].get("nb50"),
                lambda s: s["ann"].get("cr_pct"), lambda s: (s["sh_fill"] or {}).get("sat"))) + f" whale-dump {sum(1 for s in g if (s['sh_fill'] or {}).get('whale'))}")
json.dump(res, open("/home/it/sniper-data/filters3/tune/t4_live.json", "w"))
