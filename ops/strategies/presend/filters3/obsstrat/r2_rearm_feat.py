#!/usr/bin/env python3
"""r2: real money (realized) of LIVE re-arm and T2 fills by arm-time / fill-time features (DEV vs VAL). Blocking = minus the P&L."""
import json, collections, sys
HRS = {"DEV": 74.35, "VAL": 20.61}
rows = [json.loads(l) for l in open("/home/it/sniper-data/filters3/obsstrat/pos_join.jsonl")]
def tab(title, rows, keyf):
    agg = collections.defaultdict(lambda: {"DEV": [0, 0.0, 0], "VAL": [0, 0.0, 0]})
    for d in rows:
        k = keyf(d)
        if k is None: continue
        a = agg[k][d["per"]]; a[0] += 1; a[1] += d["pnl"]; a[2] += d["pnl"] > 0
    print("==", title)
    for k in sorted(agg, key=lambda z: str(z)):
        s = []
        for per in ("DEV", "VAL"):
            n, p, w = agg[k][per]
            s.append(f"{n:5d} {p:+7.3f} {1000*p/max(n,1):+6.1f}m win {w/max(n,1):.2f}")
        print(f"  {str(k):28s} | " + " | ".join(s))
RA = [d for d in rows if d["kind"] == "rearm"]; T2 = [d for d in rows if d["kind"] == "t2"]
def bucket(v, cuts):
    if v is None: return None
    for c in cuts:
        if v <= c: return f"<={c}"
    return f">{cuts[-1]}"
tab("REARM all", RA, lambda d: "all")
tab("REARM r5_skip (obs window)", RA, lambda d: (d.get("rw") or {}).get("r5_skip"))
tab("REARM fill slot - dump slot", RA, lambda d: bucket(d["fslot"] - d["dump"]["slot"], [3, 4, 5, 6, 8, 10, 13, 16, 20, 25]))
tab("REARM dump pct", RA, lambda d: bucket(d["dump"]["pct"], [7, 8, 10, 13, 20]))
tab("REARM dump drop%", RA, lambda d: bucket(d["dump"]["drop_pct"], [15, 20, 25, 30, 40]))
tab("REARM dump age_slots", RA, lambda d: bucket(d["dump"]["age_slots"], [5, 10, 20, 40, 80, 141]))
tab("REARM dump sol", RA, lambda d: bucket(d["dump"]["sol"] / 1e9, [1, 2, 3, 5, 8]))
tab("REARM n holders", RA, lambda d: bucket(len(d.get("rholders") or []), [1, 2, 3, 5]))
tab("REARM top holder pct", RA, lambda d: bucket(max([h["pct"] for h in d.get("rholders") or []] or [0]), [7, 9, 12, 16, 25]))
tab("REARM top holder role (obs)", RA, lambda d: ((sorted((d.get("rw") or {}).get("holders") or [], key=lambda h: -h["pct"]) or [{}])[0]).get("role"))
tab("REARM quiet all4 (obs)", RA, lambda d: ((d.get("rw") or {}).get("quiet") or {}).get("all4"))
tab("REARM quiet since_last (obs)", RA, lambda d: ((d.get("rw") or {}).get("quiet") or {}).get("since_last"))
tab("REARM quiet coh_hold (obs)", RA, lambda d: bucket(((d.get("rw") or {}).get("quiet") or {}).get("coh_hold"), [0, 1, 2]))
tab("REARM dump vsol", RA, lambda d: bucket(d["dump"]["vsol"] / 1e9, [32, 36, 40, 50, 60]))
tab("REARM seller still holds", RA, lambda d: None)
tab("T2 slots_after_trigger", T2, lambda d: bucket(d.get("sat"), [2, 3, 4, 5, 6, 7, 8, 9, 10, 12]))
tab("REARM path", RA, lambda d: d.get("path"))
tab("T2 path", T2, lambda d: d.get("path"))
