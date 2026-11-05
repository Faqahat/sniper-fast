#!/usr/bin/env python3
"""SL-REDFLAGS s4: univariate scan of candidate signing-time red flags: SL hit rate and realized P&L inside the flag,
FIT (r37..r42) vs VAL (r43..r49). saved = -(sum realized P&L of flagged trades)."""
import json, collections
R = [json.loads(l) for l in open("/home/moiz/sniper-data/filters3/slflags/rows.jsonl")]
def g(d, k, z=None):
    v = d.get(k); return z if v is None else v
FL = {
 "whale_n>=10": lambda d: d["kind"] == "t2" and g(d, "whale_n", -1) >= 10,
 "whale_n>=13": lambda d: d["kind"] == "t2" and g(d, "whale_n", -1) >= 13,
 "whale_n<=1": lambda d: d["kind"] == "t2" and 0 <= g(d, "whale_n", -1) <= 1,
 "co_whale>=5": lambda d: g(d, "co_whale", 0) >= 5,
 "co_whale>=10": lambda d: g(d, "co_whale", 0) >= 10,
 "age>=300&n120<=3": lambda d: g(d, "age", 0) >= 300 and g(d, "n120", 99) <= 3,
 "age>=1000": lambda d: g(d, "age", 0) >= 1000,
 "age>=300": lambda d: g(d, "age", 0) >= 300,
 "n120<=3": lambda d: d["kind"] == "t2" and g(d, "n120", 99) <= 3,
 "n120>=40": lambda d: d["kind"] == "t2" and g(d, "n120", 0) >= 40,
 "max_oth>=12": lambda d: g(d, "max_oth", 0) >= 12,
 "sum_oth>=30": lambda d: g(d, "sum_oth", 0) >= 30,
 "n_oth6>=2": lambda d: g(d, "n_oth6", 0) >= 2,
 "w_pct>=12": lambda d: g(d, "w_pct", 0) >= 12,
 "trig_vsol>=45": lambda d: g(d, "trig_vsol", 0) >= 45,
 "trig_sol>=6": lambda d: g(d, "trig_sol", 0) >= 6,
 "dd120>=0.3": lambda d: d["kind"] == "t2" and g(d, "dd120", 0) >= 0.3,
 "sign_after>=6": lambda d: g(d, "sign_after_trig", 0) >= 6,
 "nb50<=4": lambda d: g(d, "nb50", 99) <= 4,
 "coh_hold>=2": lambda d: d["kind"] == "t2" and g(d, "coh_hold", 0) >= 2,
 "wh_dumps>=10": lambda d: d["kind"] == "t2" and g(d, "wh_dumps", 0) >= 10,
 "since_last==0": lambda d: d["kind"] == "t2" and g(d, "since_last", 9) == 0,
 "bot_other>=10": lambda d: g(d, "sum_bot", 0) >= 10,
 "rearm": lambda d: d["kind"] == "rearm",
 "sum_fresh>=15": lambda d: g(d, "sum_fresh", 0) >= 15,
 "cr_pct>=5": lambda d: g(d, "cr_pct", 0) >= 5,
}
def grp(d): return "FIT" if d["run"] <= 42 else "VAL"
SL = lambda d: d["exit"] in ("stop-loss", "sl")
tot = collections.defaultdict(lambda: [0, 0, 0.0, 0])
for d in R:
    t = tot[grp(d)]; t[0] += 1; t[1] += SL(d); t[2] += d["pnl"]; t[3] += d["pnl"] < -0.08
for k, t in sorted(tot.items()): print(f"{k}: n {t[0]} SL {t[1]} ({100*t[1]/t[0]:.1f}%) big<-0.08 {t[3]} pnl {t[2]:+.2f}")
print(f"{'flag':20s} | FIT n  SL  SLrate  lift  saved  winlost | VAL n  SL  SLrate lift saved winlost")
for name, fn in FL.items():
    row = []
    for G in ("FIT", "VAL"):
        xs = [d for d in R if grp(d) == G and fn(d)]
        n = len(xs); s = sum(SL(d) for d in xs); p = sum(d["pnl"] for d in xs); wl = sum(d["pnl"] for d in xs if d["pnl"] > 0)
        base = tot[G][1] / tot[G][0]
        row.append(f"{n:5d} {s:3d} {100*s/max(n,1):5.1f}% {(s/max(n,1))/base:4.1f}x {-p:+6.2f} {wl:5.2f}")
    print(f"{name:20s} | " + " | ".join(row))
