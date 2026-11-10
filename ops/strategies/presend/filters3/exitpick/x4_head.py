#!/usr/bin/env python3
"""EXIT-125v200 step 4: every real fill re-priced under each exit setting (one is its real setting, the rest counterfactual).
Settings: timer H ms (pure timer, TP +20 / SL -20 kept) and slot-N (decision when the engine first sees slot fill+N; TP/SL kept).
Decision -> landing:
  own   : the fill's own measured decision->land lag; a timer decision keeps the fill's own timer delay (real decision - fill - N)
  resamp: 25 draws of (timer delay, lag) pairs from the run's own time-exits (pooled over all runs when a run has < 30) - robustness
TP/SL: engine marks recomputed on the tape with our real sell removed; whichever of TP/SL/timer fires first wins.
Price: curve state at the cf landing rx time (xlib.state_at, validated 1915/1915 exact at the real landing), net = real realized
P&L + (cf gross - real gross) x (1 - 1.25%); sell tx costs and buy side unchanged.  +ATA rent back as in the run reports.
Coverage: the hold tape holds every trade up to fill + 3000 ms; a landing after that = not covered (counted, never extrapolated),
unless raw-tape rows from x5 are present (rawext.json).
fc20: stress variant, every other buy after our fill gets 20% fewer tokens (followers smaller), marks and price both.
Out: cf.json"""
import json, sys, random, collections, os
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/filters3/exit125")
import xlib as X
D = "/home/it/sniper-data/filters3/exit125"
J = json.load(open(f"{D}/fills.json")); F = J["fills"]
SM = {int(k): v for k, v in json.load(open(f"{D}/slotmap.json")).items()}
RAW = json.load(open(f"{D}/rawext.json")) if os.path.exists(f"{D}/rawext.json") else {}
TIMERS = [100, 125, 150, 200, 250, 300, 400, 600, 800, 1000, 1500, 2000]
SLOTS = [1, 2, 3, 4, 5]
FEE = 0.0125
TAPE_MS = 3000.0
random.seed(7)

# per-run (timer delay, lag) pairs from real time exits
pairs = collections.defaultdict(list)
for x in F:
    if x["exit"] and x["exit"]["why"] == "time-ms" and x["sells"]:
        pairs[x["run"]].append(((x["exit"]["t"] - x["t"]) / 1e6 - x["timer"], (x["sells"][0]["t"] - x["exit"]["t"]) / 1e6))
allp = [p for v in pairs.values() for p in v]
def pool(r): return pairs[r] if len(pairs[r]) >= 30 else allp

SLOT_MS = 204.0   # median slot length seen in these runs (first-seen times, x3)
def slot_obs(P, s):
    c = [SM[s][0]] if s in SM else []
    c += [a["t"] for a in P["tr"] if a["slot"] == s and not a.get("raw")]
    return min(c) if c else None

def slot_start(P, s):
    """first-seen rx time of slot s; missing -> linear between the nearest observed slots (else +-204 ms per slot)"""
    v = slot_obs(P, s)
    if v is not None: return v
    lo = next(((k, slot_obs(P, k)) for k in range(s - 1, s - 6, -1) if slot_obs(P, k) is not None), None)
    hi = next(((k, slot_obs(P, k)) for k in range(s + 1, s + 6) if slot_obs(P, k) is not None), None)
    if lo and hi: return lo[1] + (hi[1] - lo[1]) * (s - lo[0]) / (hi[0] - lo[0])
    if lo: return lo[1] + (s - lo[0]) * SLOT_MS * 1e6
    if hi: return hi[1] - (hi[0] - s) * SLOT_MS * 1e6
    return None

def extend(x, P):
    """append raw-tape trades past the hold tape (rx time = slot start + idx share of the slot; never before fill + 3000 ms).
    Returns the covered horizon in ms after the fill."""
    rw = RAW.get(x["sig"])
    if not rw or not rw["slot_maxidx"] or x.get("tape_src"): return x.get("tape_ms") or TAPE_MS, False
    tr = P["tr"]; have = {(a["slot"], a["idx"], a.get("j", 0)) for a in tr}
    last = max(a["slot"] for a in tr)
    own = {x["sig"], x["sells"][0]["sig"]}
    smax = {int(k): v for k, v in rw["slot_maxidx"].items()}
    add = []
    for a in rw["trades"]:
        k = (a["slot"], a["idx"], a["j"])
        if k in have or a["sig"] in own or a["slot"] < last: continue
        st = slot_start(P, a["slot"])
        if st is None: continue
        t = st + (a["idx"] / (smax.get(a["slot"], a["idx"]) + 1)) * SLOT_MS * 1e6
        add.append(dict(a, t=max(int(t), x["t"] + int(TAPE_MS * 1e6) + 1), raw=True))
    if not add and max(smax) <= last: return TAPE_MS, False
    allt = sorted(tr + add, key=lambda a: (a["slot"], a["idx"], a.get("j", 0)))
    P["fi"] = next(i for i, a in enumerate(allt) if a["sig"] == x["sig"])
    P["si"] = next(i for i, a in enumerate(allt) if a["sig"] == x["sells"][0]["sig"] and not a["buy"])
    P["tr"] = allt
    end = slot_start(P, max(smax) + 1)
    return (max(TAPE_MS, (end - x["t"]) / 1e6) if end else TAPE_MS), bool(add)

def price(x, P, land_t, fc):
    """gross SOL of our sell landing at land_t, or None when the landing is past the covered tape"""
    if (land_t - x["t"]) / 1e6 > P["cov_ms"]:
        return None
    vsol, vtok, ri, _ = X.state_at(P, land_t, follow_cut=fc)
    return X.gross_out(P["q"], vsol, vtok)

def run_setting(x, P, kind, val, dly, lag, fc, marks):
    """returns (decision why, decision t, land t, gross) for one setting"""
    if kind == "timer":
        d = x["t"] + (val + dly) * 1e6
    else:
        d = slot_start(P, x["slot"] + val)
        if d is None: return None
        d = max(d, x["t"])
    why = "time"
    for t, v, i in marks:
        if t >= d: break
        if v >= 1.2 or v <= 0.8:
            d, why = t, ("tp" if v >= 1.2 else "sl"); break
    land = d + lag * 1e6
    g = price(x, P, land, fc)
    return why, d, land, g

