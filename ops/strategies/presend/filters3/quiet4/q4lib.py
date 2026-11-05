"""QUIET4 common: load the x1 extracts, periods, the LIVE baseline (what r49/r50 run: QUIET + QUIET3-A + creator ledger 2:0.05),
online ledgers and the scoring table. Money = presend_live_realized (each run at its own exit: r48/r49 125 ms, the rest 200 ms)."""
import pickle, collections
from datetime import datetime, timezone, timedelta
PKT = timezone(timedelta(hours=5))
D = "/home/moiz/sniper-data/filters3/quiet4"
RUNS = ["r37", "r38", "r39", "r40", "r41", "r42", "r43", "r44", "r45", "r46", "r47", "r48", "r49", "r50"]
CUT = datetime(2026, 11, 1, 12, 0, tzinfo=PKT).timestamp() * 1e9
ATT0 = datetime(2026, 11, 2, 8, 0, tzinfo=PKT).timestamp() * 1e9
ATT1 = datetime(2026, 11, 2, 8, 40, tzinfo=PKT).timestamp() * 1e9
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
PERS = ["DEV", "VAL", "HOLD", "R50"]


def pkt(t): return datetime.fromtimestamp(t / 1e9, PKT).strftime("%m-%d %H:%M:%S")


def period(run, t):
    if run == "r50": return "R50"
    if run in RUNS[6:13]: return "HOLD"
    if run == "r42" and t >= CUT: return "VAL"
    return "DEV"


_X = {}
def load(run):
    if run not in _X: _X[run] = pickle.load(open(f"{D}/ex_{run}.pkl", "rb"))
    return _X[run]


def q3a(p):
    """QUIET3-A exactly as the engine (T2; n_120s <= 15 and wh_dumps <= 3, QUIET's rule on)"""
    if p["kind"] != "T2": return False
    v, q = p["v2"] or {}, p["quiet"] or {}
    n, wd = v.get("n_120s"), q.get("wh_dumps")
    return n is not None and wd is not None and q.get("rule_on") is not False and n <= 15 and wd <= 3


def all_positions():
    """every live position r37..r50 in time order with period, attack flag, spans"""
    P = []
    for r in RUNS:
        for p in load(r)["pos"]:
            p = dict(p); p["per"] = period(r, p["t0"]); p["attk"] = r == "r42" and ATT0 - 60e9 <= p["t0"] <= ATT1 + 60e9; P.append(p)
    P.sort(key=lambda p: (p["t0"], p["buy_t"]))
    for i, p in enumerate(P): p["id"] = i
    return P


def baseline(P):
    """mark p['base_block'] = what the live r49/r50 config would have blocked before this position existed:
    QUIET3-A (simulated r37..r48; live in r49/r50 so every r49/r50 position passed it) and the creator ledger cr-loss 2:0.05
    (simulated r37..r46 online from kept positions, carried across runs; live r47..r50 = they passed it). Blocked positions never
    enter any history. QUIET skip + stop were live in every run (all positions passed them)."""
    led = collections.defaultdict(list)   # creator -> [(known, pnl)]
    for p in P:
        b = None
        if p["run"] not in ("r49", "r50") and q3a(p): b = "q3a"
        if b is None and p["run"] in RUNS[:10] and p["creator"]:
            h = [x for x in led[p["creator"]] if x[0] < p["t0"]]
            if len(h) >= 2 and sum(x[1] for x in h) <= -0.05: b = "crloss"
        p["base_block"] = b
        if b is None and p["creator"]: led[p["creator"]].append((p["known"], p["pnl"]))
    return [p for p in P if p["base_block"] is None]


SPAN_H = {}
def spans(P):
    """hours of live trading per period = sum over runs of (last - first trigger) in that period"""
    by = collections.defaultdict(list)
    for p in P: by[(p["per"], p["run"])].append(p["t0"])
    h = collections.Counter()
    for (per, run), ts in by.items(): h[per] += (max(ts) - min(ts)) / 3.6e12
    return h


def summ(blocked, H, per):
    v = [p["pnl"] for p in blocked]
    s = sorted(v, reverse=True)
    win = [x for x in v if x > 0]; los = [x for x in v if x <= 0]
    saved = -sum(v)
    # w/o top 5 = drop the 5 best trades of the WHOLE period's kept set? we use the standard: the 5 biggest blocked winners removed
    # AND (conservative) the 5 biggest blocked losers removed -> report both
    wo5_l = -sum(sorted(v)[5:])           # without the 5 biggest losses blocked (the saves' top 5)
    return {"n": len(v), "nw": len(win), "w": sum(win), "nl": len(los), "l": sum(los), "saved": saved, "wo5": wo5_l,
            "day": saved / H.get(per, 1e9) * 24 if H.get(per) else 0.0}


def table(name, P, blk_ids, H, extra=""):
    out = {}
    line = f"{name:<44}"
    for per in PERS:
        b = [p for p in P if p["per"] == per and p["id"] in blk_ids]
        s = summ(b, H, per); out[per] = s
        line += f" | {per} {s['n']:3d} w{s['nw']:3d}{s['w']:+.2f} l{s['nl']:3d}{s['l']:+.2f} ={s['saved']:+.3f} w5 {s['wo5']:+.3f} {s['day']:+.2f}/d"
    print(line + extra, flush=True)
    return out
