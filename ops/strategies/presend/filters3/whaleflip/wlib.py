"""WHALEFLIP shared helpers: load w1's filled windows, periods (DEV / VAL / HOLDOUT, BRIEF + agent task), hours, stats."""
import pickle, glob, collections, json
D = "/home/it/sniper-data/filters3/whaleflip"
CUT = 1793516400            # 11-01 12:00 PKT (07:00 UTC): DEV / VAL boundary inside r42
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
SUP = 1e15


def period(f):
    r = f["run"]; t = f["fills"][0]["t"] / 1e9
    if r <= 41: return "DEV"
    if r == 42: return "DEV" if t < CUT else "VAL"
    return "HOLD"


def seg(f):
    """run segment name (r42 split at the DEV/VAL cut)"""
    if f["run"] == 42: return "r42a" if f["fills"][0]["t"] / 1e9 < CUT else "r42b"
    return f"r{f['run']}"


def load(runs=range(39, 49)):
    out = []
    for r in runs:
        out += pickle.load(open(f"{D}/fills_r{r}.pkl", "rb"))["fills"]
    for f in out:
        f["mint"] = f["fills"][0].get("mint") or f.get("mint") or (f.get("trig") or {}).get("mint")
        f["period"] = period(f); f["seg"] = seg(f)
    return out


def hours(fills):
    """live hours per segment (first fill -> last fill of the segment; r42 split at CUT) and per period"""
    ts = collections.defaultdict(list)
    for f in fills: ts[f["seg"]].append(f["fills"][0]["t"] / 1e9)
    h = {}
    for s, v in ts.items():
        lo, hi = min(v), max(v)
        if s == "r42a": hi = CUT
        if s == "r42b": lo = CUT
        h[s] = (hi - lo) / 3600
    P = {"DEV": ["r39", "r40", "r41", "r42a"], "VAL": ["r42b"], "HOLD": ["r43", "r44", "r45", "r46", "r47", "r48"]}
    hp = {p: sum(h.get(s, 0) for s in ss) for p, ss in P.items()}
    return h, hp, P


def st(v, hrs=None):
    """n, sum, mean mSOL, win %, w/o top 5, SOL/day"""
    v = list(v)
    if not v: return {"n": 0, "sum": 0.0, "mean_msol": 0.0, "win": 0.0, "wo_top5": 0.0, "sol_day": None}
    s = sorted(v)
    o = {"n": len(v), "sum": round(sum(v), 4), "mean_msol": round(sum(v) / len(v) * 1000, 2), "win": round(sum(x > 0 for x in v) / len(v), 3),
         "wo_top5": round(sum(s[:-5]), 4)}
    o["sol_day"] = round(sum(v) / hrs * 24, 3) if hrs else None
    return o


def fmt(o):
    if not o["n"]: return "n 0"
    return f"n {o['n']:4d} {o['sum']:+7.3f} ({o['mean_msol']:+6.1f} mSOL, win {o['win']:.0%}, w/o top5 {o['wo_top5']:+7.3f}" + (f", {o['sol_day']:+.2f}/day)" if o.get("sol_day") is not None else ")")
