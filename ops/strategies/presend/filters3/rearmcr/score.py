#!/usr/bin/env python3
"""REARM-CREATOR step 4: score "skip a re-arm window when the creator holds >= X% at arm" (+ creator-is-the-holder variants)
on REAL realized P&L of the re-arm fills it would block. DEV / VAL / HOLDOUT per the filters3 proof rules.
usage: score.py [--holdout]   (without --holdout the HOLDOUT columns are not printed)"""
import json, sys, collections
D = "/home/moiz/sniper-data/filters3/rearmcr"
HOLD = "--holdout" in sys.argv
R = json.load(open(f"{D}/rows.json"))
# r38 creators (no ann): from the launch collector
need = {x["mint"] for x in R["rearm"] if x["creator"] is None}
cre = {}
for l in open("/home/moiz/sniper-data/collect/run_20261029_1400/launches.jsonl"):
    i = l.find('"mint":"'); m = l[i + 8:l.find('"', i + 8)]
    if m in need: cre[m] = json.loads(l)["creator"]
for x in R["rearm"]:
    if x["creator"] is None: x["creator"] = cre.get(x["mint"])
def hset(x): return [w for w, p in x["holders"]]
RULES = {
    "cr>=3": lambda x: x["cr_pct"] >= 3, "cr>=6": lambda x: x["cr_pct"] >= 6, "cr>=10": lambda x: x["cr_pct"] >= 10,
    "cr>=15": lambda x: x["cr_pct"] >= 15, "cr>=20": lambda x: x["cr_pct"] >= 20,
    "cr_in_holders": lambda x: x["creator"] in hset(x),
    "cr_only_holder": lambda x: hset(x) == [x["creator"]],
    "cr_only_holder&>=10": lambda x: hset(x) == [x["creator"]] and x["cr_pct"] >= 10,
    "cr_largest_holder": lambda x: bool(x["holders"]) and x["holders"][0][0] == x["creator"],
}
spans = R["spans"]
def days(per, runs=None):
    s = 0.0
    for k, (a, b) in spans.items():
        r = int(k[1:3])
        p = "DEV" if (r <= 41 or k == "r42DEV") else "VAL" if k == "r42VAL" else "HOLD"
        if r < 38: continue
        if p == per and (runs is None or r in runs): s += (b - a) / 1e9 / 86400
    return s
fills = [x for x in R["rearm"] if x["filled"] and x["pnl"] is not None]
nofill_real = [x for x in R["rearm"] if x["filled"] and x["pnl"] is None]
print(f"re-arm windows {len(R['rearm'])}, filled {sum(x['filled'] for x in R['rearm'])}, with realized {len(fills)}, filled w/o realized {len(nofill_real)}")
print("cr_pct source:", collections.Counter((x["src"]) for x in fills))
pers = ["DEV", "VAL"] + (["HOLD"] if HOLD else [])
dd = {p: days(p) for p in pers}
print("days:", {p: round(v, 2) for p, v in dd.items()})
def stat(xs):
    n = len(xs); s = sum(x["pnl"] for x in xs); w = sum(1 for x in xs if x["pnl"] > 0)
    srt = sorted(x["pnl"] for x in xs)            # most negative first = biggest saves
    s5 = sum(srt[5:]) if n > 5 else 0.0
    return n, s, w, s5
print("\nALL re-arm fills by period (baseline):")
for p in pers:
    n, s, w, _ = stat([x for x in fills if x["per"] == p]); print(f"  {p}: n {n}  pnl {s:+.3f}  win {100*w/max(n,1):.0f}%  {s/dd[p]:+.3f}/day")
print("\nRULE (blocked re-arm fills: n, their real pnl, win%, SAVED = -pnl, saved w/o top-5 saves, saved SOL/day)")
res = {}
for name, f in RULES.items():
    row = []
    for p in pers:
        xs = [x for x in fills if x["per"] == p and f(x)]
        n, s, w, s5 = stat(xs)
        row.append((p, n, s, w, s5))
        res.setdefault(name, {})[p] = {"n": n, "pnl": round(s, 4), "win": w, "saved": round(-s, 4), "saved_wo5": round(-s5, 4), "per_day": round(-s / dd[p], 4)}
    print(f"{name:22s} " + " | ".join(f"{p}: n {n:3d} pnl {s:+.3f} win {100*w/max(n,1):3.0f}% SAVED {-s:+.3f} w/o5 {-s5:+.3f} {(-s)/dd[p]:+.3f}/d" for p, n, s, w, s5 in row))
print("\nper run (blocked fills: n / saved):")
runs = sorted({x["r"] for x in fills})
for name in ["cr>=3", "cr>=6", "cr>=10", "cr>=15", "cr_only_holder", "cr_in_holders"]:
    f = RULES[name]; cells = []
    for r in runs:
        for p in pers:
            xs = [x for x in fills if x["r"] == r and x["per"] == p and f(x)]
            if any(x["r"] == r and x["per"] == p for x in fills):
                cells.append(f"r{r}{'' if r != 42 else p[0]} {len(xs)}/{-sum(x['pnl'] for x in xs):+.3f}")
    print(f"{name:16s} " + "  ".join(cells))
json.dump(res, open(f"{D}/score{'_hold' if HOLD else ''}.json", "w"), indent=1)
