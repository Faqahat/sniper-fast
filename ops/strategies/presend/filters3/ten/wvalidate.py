#!/usr/bin/env python3
"""TEN: check the window replay (wsim.py) against the LIVE windows of the recorded hours: fill agreement, money per window.
writes /home/moiz/sniper-data/filters3/ten/wval.json (per live window: kind, seg, live filled/pnl, sim filled/pnl)"""
import json, sys, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/ten")
from wsim import sim_window, dedup, SUP
import datetime
CUT = int(datetime.datetime(2026, 11, 1, 7, 0, tzinfo=datetime.timezone.utc).timestamp() * 1e9)
def seg(t): return "DEV" if t < CUT else "VAL"
REFMODE = sys.argv[1] if len(sys.argv) > 1 else "slot"
D = "/home/moiz/sniper-data/filters3/ten/"
tape = json.load(open(D + "p2tape.json"))
tape = {m: dedup(v) for m, v in tape.items()}

def covered(rows, a, b):
    """rows exist before a and after b (the recording covers the window)"""
    return rows and rows[0][0] < a - 5 and rows[-1][0] > b

out = []
for r in ["r37", "r38", "r39", "r40", "r41", "r42"]:
    X = json.load(open(D + r + ".x.json"))
    rs = X["run_start"]["presend_live"]
    qs = rs.get("quiet") or {}; t2q = tuple(int(x) for x in (qs.get("stop") or "5:2").split(":"))
    rq = tuple(int(x) for x in ((rs.get("rearm") or {}).get("quiet_stop") or "6:2").split(":"))
    for k, v in X["live"].items():
        arm = v.get("arm")
        if not arm or not v.get("disarm"): continue
        tr = arm.get("trig") or {}; m = v.get("mint") or tr.get("mint")
        rows = tape.get(m)
        if v["kind"] == "t2":
            a, b = tr.get("slot"), arm.get("en_slot")
            if a is None or b is None or not covered(rows, a, b): continue
            res = sim_window(rows, a, b, arm["spend"] / 1e9, kind="t2", whale=tr.get("wallet"), qstop=t2q, refmode=REFMODE)
        else:
            a, b = arm.get("arm_slot"), arm.get("en_slot")
            if a is None or b is None or not covered(rows, a, b): continue
            hold = {h["w"]: h["pct"] / 100 * SUP for h in (arm.get("holders") or [])}
            res = sim_window(rows, a, b, arm["spend"] / 1e9, kind="rearm", qstop=rq, holders=hold, refmode=REFMODE)
        if res is None: continue
        t = tr.get("t") or 0
        out.append({"run": r, "seg": seg(t), "kind": v["kind"], "live_filled": bool(v.get("fills")), "live_pnl": (v["pnl"] or 0) / 1e9 if v.get("fills") else 0.0,
                    "live_why": v["disarm"].get("why"), "sim_filled": res["filled"], "sim_pnl": res["pnl"], "sim_why": res.get("why"), "mint": m, "a": a, "b": b})
json.dump(out, open(D + "wval.json", "w"))
for kind in ("t2", "rearm"):
    for sg in ("DEV", "VAL"):
        W = [w for w in out if w["kind"] == kind and w["seg"] == sg]
        if not W: continue
        c = collections.Counter((w["live_filled"], w["sim_filled"]) for w in W)
        both = [w for w in W if w["live_filled"] and w["sim_filled"]]
        import statistics
        corr = statistics.correlation([w["live_pnl"] for w in both], [w["sim_pnl"] for w in both]) if len(both) > 2 else None
        print(f"{kind} {sg}: windows {len(W)} | live fill/sim fill {c[(True, True)]} | live only {c[(True, False)]} | sim only {c[(False, True)]} | neither {c[(False, False)]}"
              f" | live money {sum(w['live_pnl'] for w in W):+.3f} sim money {sum(w['sim_pnl'] for w in W):+.3f} | both-filled corr {corr if corr is None else round(corr, 2)}"
              f" live {sum(w['live_pnl'] for w in both):+.3f} sim {sum(w['sim_pnl'] for w in both):+.3f}")
        print("    sim stop reasons when live filled but sim did not:", collections.Counter(w["sim_why"] for w in W if w["live_filled"] and not w["sim_filled"]).most_common(5))
