"""EXITPICK shared helpers: load rows, split hours, policy scoring."""
import json, calendar, math, random
O = "/home/moiz/sniper-data/filters3/exitpick"
KEYS = [f"t{t}" for t in (100, 125, 150, 200, 250, 300, 400, 600, 800, 1000, 1500, 2000)] + [f"s{n}" for n in range(1, 6)]
EXT = [k for k in KEYS if k not in ("t100", "t125")]          # extension targets (s1 lands before 125 ms sometimes; kept, it is an exit choice)
HOURS = {42: 52.80, 43: 8.46, 44: 4.81, 45: 0.77, 46: 0.197, 47: 0.589, 48: 3.63, 49: 6.26, 50: 1.694}
R42_END = 1793590592930655889
DEV_CUT = calendar.timegm((2026, 11, 1, 7, 0, 0)) * 10**9
DEV_H = (DEV_CUT - (R42_END - HOURS[42] * 3600e9)) / 3600e9
SPLIT_H = dict(dev=DEV_H, val=HOURS[42] - DEV_H + HOURS[43] + HOURS[44], hold=sum(HOURS[r] for r in (45, 46, 47, 48, 49, 50)))

def load():
    return json.load(open(f"{O}/rows.json"))

def y(r, k, var="y"):
    v = r[var].get(k)
    return v if v is not None else r[var]["t125"]

def gain(r, k, var="y"):
    return y(r, k, var) - r[var]["t125"]

def feat(r, name, dl="15"):
    if name.startswith("b_"): return r["B"][dl][name]
    if name.startswith("c_"): return r["B400"]["b_" + name[2:]]
    return r["A"][name]

def boot_ci(vals, n=2000, seed=1):
    """95% bootstrap CI of the sum"""
    if not vals: return (0.0, 0.0)
    rnd = random.Random(seed); m = len(vals); s = []
    for _ in range(n):
        s.append(sum(vals[rnd.randrange(m)] for _ in range(m)))
    s.sort()
    return s[int(0.025 * n)], s[int(0.975 * n)]
