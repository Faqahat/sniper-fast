#!/usr/bin/env python3
"""TEN lever (c): MORE WINDOWS, scored by the window replay (wsim.py) and calibrated against the live windows of the same kind and
segment (live money per window / replay money per window on the live windows themselves, wval.json). ESTIMATES only.
  R-AGE   re-arm on tokens older than 141 slots (rearm_age skips, age 142..400; holders >= 6% from the token's whole history)
  R-NOH   re-arm with no >= 6% holder left (rearm_no_holder skips, age <= 141; stops: next >= 6% sell, QUIET 6:2)
  T2-W20  T2 windows 20 slots instead of 10 (live windows that expired unfilled; the extra fills after the live last slot)
Per day = estimate per window x ALL candidates of the segment (covered or not) / segment hours x 24 (coverage stated)."""
import json, sys, collections, datetime
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/ten")
from wsim import sim_window, dedup, balances, SUP, ME
D = "/home/moiz/sniper-data/filters3/ten/"
CUT = int(datetime.datetime(2026, 11, 1, 7, 0, tzinfo=datetime.timezone.utc).timestamp() * 1e9)
def seg(t): return "DEV" if t < CUT else "VAL"
H = json.load(open(D + "hours.json"))
raw = json.load(open(D + "p2tape.json"))
tape = {m: dedup(v) for m, v in raw.items()}
wval = json.load(open(D + "wval.json"))
FAILFEE = {"t2": 0.00025, "rearm": 0.00034}

def ratio(kind, sg):
    W = [w for w in wval if w["kind"] == kind and w["seg"] == sg]
    return sum(w["live_pnl"] for w in W) / len(W), sum(w["sim_pnl"] for w in W) / len(W), len(W)

def covered(rows, a, b): return rows and rows[0][0] < a - 5 and rows[-1][0] > b

res = collections.defaultdict(list)       # (lever, seg) -> [sim pnl per window]
cand = collections.Counter()               # (lever, seg) -> all candidates
for r in ["r38", "r39", "r40", "r41", "r42"]:
    X = json.load(open(D + r + ".x.json"))
    rq = tuple(int(x) for x in ((X["run_start"]["presend_live"].get("rearm") or {}).get("quiet_stop") or "6:2").split(":"))
    for x in X["rearm_skip_rows"]:
        if not x.get("slot") or not x.get("t"): continue
        sg = seg(x["t"]); age = x.get("age") or 0
        if x["why"] == "rearm_age" and 141 < age <= 400:
            lev = "R-AGE 142-200" if age <= 200 else ("R-AGE 201-300" if age <= 300 else "R-AGE 301-400")
        elif x["why"] == "rearm_no_holder" and age <= 141: lev = "R-NOH"
        else: continue
        if (x.get("vsol") or 0) >= 100e9: continue
        cand[(lev, sg)] += 1
        rows = tape.get(x["mint"]); a = x["slot"] + 3; b = a + 20
        if not covered(rows, a, b): continue
        hold = None
        if lev.startswith("R-AGE"):
            bal = balances(raw.get(x["mint"]), (x["slot"] + 2, 10**9))
            if bal is None: continue
            hold = {w: v for w, v in bal.items() if w not in (ME, "?") and v >= 0.06 * SUP}
            if not hold: continue                       # the engine's holders check would have skipped it (no_holder)
        out = sim_window(rows, a, b, 0.65, kind="rearm", qstop=rq, holders=hold)
        if out is None: continue
        res[(lev, sg)].append(out["pnl"])
    if r == "r37": continue
for r in ["r37", "r38", "r39", "r40", "r41", "r42"]:
    X = json.load(open(D + r + ".x.json"))
    qs = (X["run_start"]["presend_live"].get("quiet") or {}); t2q = tuple(int(x) for x in (qs.get("stop") or "5:2").split(":"))
    for v in X["live"].values():
        if v["kind"] != "t2" or not v.get("arm") or (v.get("disarm") or {}).get("why") != "expired": continue
        tr = v["arm"]["trig"]; sg = seg(tr["t"]); cand[("T2-W20", sg)] += 1
        rows = tape.get(v.get("mint") or tr.get("mint")); a, b = tr["slot"], v["arm"]["en_slot"]
        if not covered(rows, a, b + 10): continue
        o1 = sim_window(rows, a, b, 0.696, kind="t2", whale=tr.get("wallet"), qstop=t2q)
        if o1 is None or o1["filled"]: continue                # the replay must agree that the 10-slot window did not fill
        o2 = sim_window(rows, a, b + 10, 0.696, kind="t2", whale=tr.get("wallet"), qstop=t2q)
        res[("T2-W20", sg)].append(o2["pnl"])

print("calibration (live windows of the recorded hours): live money / window, replay money / window")
for k in ("t2", "rearm"):
    for sg in ("DEV", "VAL"):
        l, s, n = ratio(k, sg); print(f"  {k:5s} {sg}: n {n} live {1000 * l:+.2f} mSOL/window, replay {1000 * s:+.2f} -> ratio {l / s:.2f}")
print("\nlever            seg  candidates covered | replay mSOL/window fill% | ESTIMATE live mSOL/window (ratio, - failed tries) | ESTIMATE SOL/day")
summary = {}
for lev in ("R-AGE 142-200", "R-AGE 201-300", "R-AGE 301-400", "R-NOH", "T2-W20"):
    for sg in ("DEV", "VAL"):
        v = res.get((lev, sg), [])
        if not v: print(f"{lev:15s} {sg} {cand[(lev, sg)]:6d} 0"); continue
        kind = "t2" if lev.startswith("T2") else "rearm"
        l, s, _ = ratio(kind, sg)
        per = sum(v) / len(v)
        est = per * (l / s) - FAILFEE[kind]
        # w/o top 5 (on the replay values, same scaling)
        vs = sorted(v, reverse=True); per5 = sum(vs[5:]) / len(v)
        est5 = per5 * (l / s) - FAILFEE[kind]
        day = est * cand[(lev, sg)] / H[sg] * 24; day5 = est5 * cand[(lev, sg)] / H[sg] * 24
        summary[f"{lev}|{sg}"] = {"cand": cand[(lev, sg)], "covered": len(v), "replay_per": per, "est_per": est, "day": day, "day_wo5": day5}
        print(f"{lev:15s} {sg} {cand[(lev, sg)]:6d} {len(v):6d} | {1000 * per:+7.2f} {sum(1 for x in v if x != 0) / len(v):4.0%} | {1000 * est:+7.2f} (w/o top5 {1000 * est5:+6.2f}) | {day:+6.2f}/day (w/o top5 {day5:+6.2f})")
json.dump(summary, open(D + "wlevers.json", "w"), indent=1)
