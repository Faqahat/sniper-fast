"""CR-EARNBACK common: load the extracts, the periods, the calibration (shadow row c vs live on the same T2 windows), the candidate
windows (every live position + every live cr_loss / rearm_cr_loss skip) in time order."""
import pickle, json, collections
from datetime import datetime, timezone, timedelta
PKT = timezone(timedelta(hours=5))
D0 = "/home/it/sniper-data/filters3/crearn"
RUNS = [f"r{i}" for i in range(39, 51)]
SPLIT = datetime(2026, 11, 1, 12, 0, tzinfo=PKT).timestamp() * 1e9
GATE_RUNS = {"r47", "r48", "r49", "r50"}          # the live gate (dip32) ran; the state = seed (r39–r46, every position) + live
def pkt(t): return datetime.fromtimestamp(t / 1e9, PKT)
def period(run, t):
    if run in ("r39", "r40", "r41"): return "DEV"
    if run == "r42": return "DEV" if t < SPLIT else "VAL"
    return "HOLD"
_c = {}
def load(run):
    if run not in _c: _c[run] = pickle.load(open(f"{D0}/ex_{run}.pkl", "rb"))
    return _c[run]

def paper_of(X, sig, size):
    """the shadow's row c result for trigger sig scaled to `size` SOL: (filled, value SOL, exit ns) or None (shadow did not arm it)"""
    p = X["paper"].get(sig) if sig else None
    if p is None: return None
    if not p["filled"]: return (False, 0.0, None)
    v = p["net"] * size / p["sol_in"] if p["sol_in"] else p["net"]
    return (True, v, p["t_exit"])

def windows():
    """candidate windows in t0 order. Each: run, per, kind, t0, creator, sig, live (traded live: realized SOL sum or None = skipped live),
    live_known (ns), why (live skip reason), paper (filled, SOL at live size, exit ns) or None"""
    out = []
    for run in RUNS:
        X = load(run)
        # every live arm = one window; its realized positions (w, mint) summed (none: did not fill, 0)
        g = collections.defaultdict(lambda: {"pnl": 0, "n": 0, "known": 0, "fol": False, "creator": None, "pl": []})
        for p in X["pos"]:
            k = (p["w"], p["mint"]); g[k]["pnl"] += p["pnl"]; g[k]["n"] += 1; g[k]["known"] = max(g[k]["known"], p["known"]); g[k]["pl"].append((p["known"], p["pnl"] / 1e9))
            g[k]["fol"] = g[k]["fol"] or p["fol"]; g[k]["creator"] = g[k]["creator"] or p["creator"]
        seen = set()
        for a in X["arms"]:
            k = (a["w"], a["mint"])
            if k in seen: continue
            seen.add(k)
            p = g.get(k)
            size = (a["spend"] or X["spend"] or 550_000_000) / 1e9
            out.append({"run": run, "per": period(run, a["t0"]), "kind": a["kind"], "t0": a["t_dec"], "creator": a["creator"] or (p or {}).get("creator"),
                        "sig": a["sig"], "mint": a["mint"], "live": (p["pnl"] / 1e9) if p else 0.0, "filled": bool(p),
                        "live_known": p["known"] if p else None, "pl": p["pl"] if p else [], "fol": p["fol"] if p else None, "why": None,
                        "paper": paper_of(X, a["sig"], size) if a["kind"] == "t2" else None, "arm_cr": a["cr"]})
        missing = [k for k in g if k not in seen]
        if missing: print("WARN", run, len(missing), "positions without an arm")
        for s in X["skips"]:
            if s["why"] not in ("cr_loss", "rearm_cr_loss"): continue
            c = s["creator"] or X["mcre"].get(s["mint"])
            size = (X["spend"] or 550_000_000) / 1e9
            out.append({"run": run, "per": period(run, s["t0"]), "kind": s["kind"], "t0": s["t_dec"], "creator": c, "sig": s["sig"], "mint": s["mint"],
                        "live": None, "filled": None, "live_known": None, "fol": None, "why": s["why"], "paper": paper_of(X, s["sig"], size) if s["kind"] == "t2" else None,
                        "arm_cr": s["cr"], "holders": s["holders"]})
    out.sort(key=lambda w: w["t0"])
    return out

def calibration(runs=None):
    """live vs shadow row c on the same T2 live arms (live 0 when the arm did not fill, paper 0 when the shadow did not fill)"""
    res = collections.defaultdict(lambda: collections.Counter())
    for run in runs or RUNS:
        X = load(run)
        lv = collections.Counter()
        for p in X["pos"]:
            if p["kind"] == "t2": lv[p["sig"]] += p["pnl"] / 1e9
        for a in X["arms"]:
            if a["kind"] != "t2": continue
            size = (a["spend"] or X["spend"]) / 1e9
            pp = paper_of(X, a["sig"], size)
            if pp is None: continue
            per = period(run, a["t0"] or 0)
            for key in (per, "ALL", run):
                R = res[key]; R["n"] += 1; R["live"] += lv.get(a["sig"], 0.0); R["paper"] += pp[1]
                R["live_fill"] += a["sig"] in lv; R["paper_fill"] += pp[0]
                if pp[1] > 0: R["pw"] += pp[1]; R["lw"] += lv.get(a["sig"], 0.0)
                elif pp[0]: R["pl"] += pp[1]; R["ll"] += lv.get(a["sig"], 0.0)
                else: R["l_nopaper"] += lv.get(a["sig"], 0.0)
    return res
