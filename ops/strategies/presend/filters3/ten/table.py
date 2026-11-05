#!/usr/bin/env python3
"""TEN step 3: the SOL/day ladder, DEV vs VAL, per run, with and without the top 5 trades.
  today          live realized (PROVEN: real money)
  + loss filters ASSUMPTION (other agents' best case, not our work): every trade with NO other buyer within 10 slots after our buy is
                 removed (an oracle on a post-hoc feature: the ceiling of the QUIET work), plus the 11-02 attack (08:31-08:36:30 PKT)
  + WIDE-5       the wide shadow's 5-6% whale windows (age >= 2 slots), calibrated (wide_report method), minus wide fills that share a
                 token with a live window within 12 slots (conflict, conservative)  ESTIMATE; only r41/r42 have the wide shadow
  + SIZE-15      T2 trades with v2.n_tr_60s >= 15 at 1.5x size, own-tape curve replay, follower price-out beta 3  ESTIMATE
                 (applied to the trades left after the loss filters)"""
import json, sys, collections, datetime
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/ten")
from sizesim import pnl_at
D = "/home/moiz/sniper-data/filters3/ten/"
pos = json.load(open(D + "pos.json")); wide = json.load(open(D + "wide.json")); H = json.load(open(D + "hours.json"))
gap = {tuple(k.split("|")): v for k, v in json.load(open(D + "gap.json")).items()}
def T(s): return int((datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S") - datetime.timedelta(hours=5)).replace(tzinfo=datetime.timezone.utc).timestamp() * 1e9)
ATK = (T("2026-11-02 08:31:00"), T("2026-11-02 08:36:30"))

# live windows by mint (for the wide conflict rule)
lw = collections.defaultdict(list)
for r in ("r41", "r42"):
    X = json.load(open(D + r + ".x.json"))
    for v in X["live"].values():
        a = v.get("arm")
        if not a: continue
        tr = a.get("trig") or {}; s = a.get("arm_slot") or tr.get("slot")
        if s: lw[v.get("mint") or tr.get("mint")].append(s)

def wide_rows(sg, run):
    out = []
    for w in wide:
        if w["seg"] != sg or w["run"] != run or not (5 <= w["pct"] < 6) or w["age"] < 2 or w["paper"] is None: continue
        s = (w["sh_fill"] or {}).get("s_in") or 0
        if any(abs(x - s) <= 12 for x in lw.get(w["mint"], [])): continue
        out.append(w["paper"] + gap[(sg, run)])
    return out

def lossf(p): return p["n_fol10"] == 0 or ATK[0] <= p["t"] <= ATK[1]
def size15(p): return p["kind"] == "t2" and ((p["v2"] or {}).get("n_tr_60s") or -1) >= 15

def fmt(v, h):
    if v is None: return "      n/a      "
    s = sorted(v, reverse=True)
    return f"{sum(v) / h * 24:+6.2f} ({sum(s[5:]) / h * 24:+6.2f})"

rows = []
def ladder(label, P, hrs, sg, runs):
    today = [p["pnl"] for p in P]
    kept = [p for p in P if not lossf(p)]
    lf = [p["pnl"] for p in kept]
    wv = None
    if any(r in ("r41", "r42") for r in runs):
        wv = []
        for r in runs:
            if r in ("r41", "r42"): wv += wide_rows(sg, r)
    sz = [pnl_at(p, p["spend"] * 1.5, 0.0, 0, 3.0)[0] - p["pnl"] if size15(p) else 0.0 for p in kept]
    sz_s = [pnl_at(p, p["spend"] * 1.5, 0.2, 7, 3.0)[0] - pnl_at(p, p["spend"], 0.2, 7, 0.0)[0] if size15(p) else 0.0 for p in kept]
    a = lf + (wv or [])
    b = a + sz
    print(f"{label:9s} {hrs:5.1f} h n {len(today):4d} | today {fmt(today, hrs)} win {sum(1 for x in today if x > 0) / max(1, len(today)):.0%} | +loss filters (ASSUMED) {fmt(lf, hrs)}"
          f" | +WIDE-5 (EST) {fmt(a, hrs) if wv is not None else '      n/a      '} [wide alone {fmt(wv, hrs)}]"
          f" | +SIZE-15 (EST) {fmt(b, hrs)} [size alone {sum(sz) / hrs * 24:+.2f}, -20% fol {sum(sz_s) / hrs * 24:+.2f}]")

print("SOL/day (without top 5 in brackets).  today = PROVEN real money; loss filters = ASSUMPTION; WIDE-5 and SIZE-15 = ESTIMATES")
for sg in ("DEV", "VAL"):
    runs = sorted({p["run"] for p in pos if p["seg"] == sg})
    for r in runs:
        ladder(f"{sg} {r}", [p for p in pos if p["seg"] == sg and p["run"] == r], H[f"{sg}:{r}"], sg, [r])
    ladder(f"{sg} ALL", [p for p in pos if p["seg"] == sg], H[sg], sg, runs)
    if sg == "DEV":
        rr = ("r41", "r42")
        ladder("DEV r41+42", [p for p in pos if p["seg"] == sg and p["run"] in rr], H["DEV:r41"] + H["DEV:r42"], sg, list(rr))
P = [p for p in pos if p["seg"] == "VAL" and not (ATK[0] <= p["t"] <= ATK[1])]
print(f"\nVAL without the attack window: today {sum(p['pnl'] for p in P) / H['VAL'] * 24:+.2f}/day (n {len(P)})")
