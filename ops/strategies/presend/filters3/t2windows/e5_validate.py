#!/usr/bin/env python3
"""T2-WINDOWS step 5: VALIDATION before any variant.
 (1) real-try replay picks the live fill (same signature) on the live windows with a tape
 (2) sim replay (simulated tries, live mechanics, run's own size + exit) vs live realized on the same live windows, per run / kind
 (3) tape holders vs the engine's re-arm holders; R5 / QUIET / QUIET3-A / lone-whale / creator proxies vs the engine's logged values
Out: /home/moiz/sniper-data/filters3/t2windows/validate.json"""
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/t2windows")
import t2lib as L, t2score as S

X, P = S.load()
ok = [x for x in X if not x.get("err")]
V = {}
# (1)
lv = [x for x in ok if x["live"] and "real_fill" in x]
agree = collections.Counter((x["c"], x["real_fill"] == x.get("live_fill_sig")) for x in lv)
V["real_replay"] = {f"{k[0]}_{'same' if k[1] else 'diff'}": n for k, n in agree.items()}
print("(1) real-try replay = live fill:", dict(agree))
# (2) per run x kind: live realized vs sim (no fees: realized has none)
rows = collections.defaultdict(lambda: collections.defaultdict(float))
for x in lv:
    mech = "m0" if x["c"] == "re" else "own"
    v, p = S.money(x, P, mech, 0, fees=False)
    k = (x["run"], x["per"], x["c"])
    rows[k]["n"] += 1; rows[k]["live"] += x["live_pnl"] or 0.0; rows[k]["sim"] += v
    rows[k]["live_fills"] += 1 if x["live_fill"] else 0; rows[k]["sim_fills"] += p
    rows[k]["fees"] += x["sims"][mech].get("fails", 0) * L.FAIL / 1e9
print("(2) sim vs live on live-armed windows (SOL; live realized has no failed-try fees)")
print(f"{'run':>4} {'per':>7} {'kind':>4} {'win':>5} {'liveF':>6} {'simF':>7} {'live':>8} {'sim':>8} {'gap/win mSOL':>12} {'fees':>6}")
tot = collections.defaultdict(lambda: collections.defaultdict(float))
V["sim_vs_live"] = []
for k in sorted(rows):
    d = rows[k]
    print(f"{k[0]:>4} {k[1]:>7} {k[2]:>4} {int(d['n']):>5} {int(d['live_fills']):>6} {d['sim_fills']:>7.1f} {d['live']:>+8.3f} {d['sim']:>+8.3f} {(d['live'] - d['sim']) / d['n'] * 1e3:>+12.2f} {d['fees']:>6.3f}")
    V["sim_vs_live"].append({"run": k[0], "per": k[1], "kind": k[2], **{a: round(b, 4) for a, b in d.items()}})
    for a, b in d.items(): tot[(k[1], k[2])][a] += b
for k in sorted(tot):
    d = tot[k]
    print(f"  {k[0]:>7} {k[1]:>4} win {int(d['n'])} live fills {int(d['live_fills'])} sim {d['sim_fills']:.1f} | live {d['live']:+.3f} sim {d['sim']:+.3f} gap/win {(d['live'] - d['sim']) / d['n'] * 1e3:+.2f} mSOL")
V["sim_vs_live_tot"] = {f"{a}_{b}": {k: round(v, 4) for k, v in d.items()} for (a, b), d in tot.items()}
# (3a) holders
hv = collections.Counter()
for x in ok:
    if x["c"] != "re": continue
    rec = (x["rec"] or {}).get("holders")
    tape6 = {w for w, p in x.get("h", []) if p >= 6.0}
    if rec is not None:
        r6 = {h["w"] for h in rec}
        hv["rec_vs_tape_same" if r6 == tape6 else "rec_vs_tape_diff"] += 1
    if x["why"] == "rearm_no_holder": hv["nohold_tape_none" if not tape6 else "nohold_tape_has6"] += 1
V["holders"] = dict(hv); print("(3a) holders:", dict(hv))
# (3b) R5 proxy vs logged (r48+)
rv = collections.Counter()
for x in ok:
    if x["c"] != "re": continue
    r5 = (x["rec"] or {}).get("r5")
    if r5 and "r5p" in x: rv[(r5["all4"], x["r5p"]["all4"])] += 1
V["r5"] = {str(k): n for k, n in rv.items()}; print("(3b) R5 logged vs proxy (logged, proxy):", dict(rv))
# (3c) QUIET / Q3A / nb50 / creator proxies on T2 triggers
qv = collections.Counter(); q3 = collections.Counter(); nb = collections.Counter(); crv = collections.Counter(); sl = collections.Counter(); ch = collections.Counter(); wf = collections.Counter()
for x in ok:
    if x["c"] != "t2": continue
    q = (x["rec"] or {}).get("quiet") or {}
    if "all4" in q:
        px = x["since_last"] >= 1 and x["coh"] == 0 and x["wh_fol"] < 4.0
        qv[(q["all4"], px)] += 1
        sl[(q.get("since_last", 0) >= 1, x["since_last"] >= 1)] += 1
        ch[(q.get("coh_hold", 0) == 0, x["coh"] == 0)] += 1
        wf[(q.get("wh_fol", -1) < 4.0, x["wh_fol"] < 4.0)] += 1
    f3 = (x["rec"] or {}).get("f3") or {}
    if "q3a" in f3 and f3.get("n_120s") is not None:
        q3[(f3["q3a"], x["n120"] <= 15 and x["wh_dumps"] <= 3)] += 1
    n = (x["rec"] or {}).get("nb")
    if n is not None: nb[(n <= 1, x["nb50"] <= 1)] += 1
    c = (x["rec"] or {}).get("creator")
    if c and x.get("creator"): crv[c == x["creator"]] += 1
for nm, c in (("quiet_all4", qv), ("since_last>=1", sl), ("coh==0", ch), ("wh_fol<4", wf), ("q3a", q3), ("lone(nb<=1)", nb), ("creator_same", crv)):
    tot_ = sum(c.values()); agr = sum(n for k, n in c.items() if (k is True) or (isinstance(k, tuple) and k[0] == k[1]))
    print(f"(3c) {nm:>14}: agree {agr}/{tot_} ({agr / max(1, tot_):.1%})  {dict(c)}")
    V[nm] = {"agree": agr, "n": tot_, "cells": {str(k): n for k, n in c.items()}}
json.dump(V, open(f"{L.D}/validate.json", "w"), indent=1, default=str)
