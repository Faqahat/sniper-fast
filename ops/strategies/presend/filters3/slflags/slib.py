"""SL-REDFLAGS shared: rows, groups, the guards already decided (QUIET3-A, creator ledger G1, fresh G3, breaker G4)."""
import json, collections
from datetime import datetime, timezone, timedelta
PKT = timezone(timedelta(hours=5))
SPLIT = 1793516400000000000
def rows():
    R = [json.loads(l) for l in open("/home/it/sniper-data/filters3/slflags/rows.jsonl")]
    R.sort(key=lambda d: d["t"])
    for d in R:
        d["grp"] = "FIT" if d["run"] <= 42 else "VAL"
        d["rk"] = f"r{d['run']}" if d["run"] != 42 else ("r42a" if d["t"] < SPLIT else "r42b")
        d["sl"] = d["exit"] in ("stop-loss", "sl")
    return R
def g(d, k, z=0):
    v = d.get(k); return z if v is None else v
def qa(d):  # QUIET3-A (T2): n_120s <= 15 and wh_dumps <= 3, QUIET rule on
    return d["kind"] == "t2" and d.get("qrule") is not False and d.get("n120") is not None and d["n120"] <= 15 \
        and d.get("wh_dumps") is not None and d["wh_dumps"] <= 3
def g3(d): return g(d, "sum_fresh") >= 35.0
def mark_prior(R, extra=None):
    """sets d['prior'] = name of the first existing guard that blocks it (QA, G1 creator ledger, G3 fresh, G4 breaker; breaker
    sequential over the trades let through by everything else incl. `extra`). Ledger: creator realized sum <= -0.10 over our earlier
    positions known at fill t + held + 4 s (all positions feed it, blocked or not, like the TAIL chain)."""
    led = collections.defaultdict(float); pend = []; losses = []; pause_until = 0
    for d in R:
        t = d["t"]
        pend.sort()
        while pend and pend[0][0] <= t:
            _, c, p = pend.pop(0); led[c] += p
        cr = d.get("creator")
        why = None
        if qa(d): why = "QA"
        elif cr and led[cr] <= -0.10: why = "G1"
        elif g3(d): why = "G3"
        elif t < pause_until: why = "G4"
        elif extra and extra(d): why = "X"
        d["prior"] = why
        if cr: pend.append((t + int(((d.get("o_held") or 0.3) + 4) * 1e9), cr, d["pnl"]))
        if why is None:
            if d["pnl"] <= -0.20:
                losses = [x for x in losses if x > t - 600e9] + [t]
                if len(losses) >= 2: pause_until = t + 1800e9; losses = []
def ts(t): return datetime.fromtimestamp(t / 1e9, PKT).strftime("%m-%d %H:%M")
