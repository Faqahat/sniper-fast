#!/usr/bin/env python3
"""TAIL t8: robustness of the candidate guards: VAL without the 11-02 attack window (08:28-08:37 PKT), 6-hour blocks helped / hurt,
permutation p (random sets of the same size from the same set: share with saved >= observed), exact-feature check on recorded hours."""
import sys, json, random, collections
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/filters3/tail")
import t5_guards as G
from t6_breaker import Brk
from datetime import datetime, timezone, timedelta
PKT = timezone(timedelta(hours=5))
A0 = datetime(2026, 11, 2, 8, 28, tzinfo=PKT).timestamp() * 1e9; A1 = datetime(2026, 11, 2, 8, 37, tzinfo=PKT).timestamp() * 1e9
rows = G.rows
raw = {(o["rk"], round(o["pnl"], 9)): o for o in json.load(open(f"{G.T}/rawcheck.json"))}
def blocks(pred, seq=None):
    if seq:
        s = seq(); out = set()
        for r in rows:
            b = s.decide(r)
            if b: out.add(id(r))
            else: s.taken(r)
        return out
    return {id(r) for r in rows if r["F"].get("has_ann") and pred(r["F"], r)} | {id(r) for r in rows if not r["F"].get("has_ann") and pred.__dict__.get("noann") and pred(r["F"], r)}
def rep(name, pred=None, seq=None, need_ann=True):
    B = blocks(pred, seq)
    random.seed(7)
    s = f"{name:34s}"
    for st, sel in (("DEV", lambda r: r["set"] == "DEV"), ("VAL", lambda r: r["set"] == "VAL"), ("VALx", lambda r: r["set"] == "VAL" and not (A0 <= r["t"] <= A1))):
        R = [r for r in rows if sel(r) and (not need_ann or r["F"].get("has_ann") or seq)]
        b = [r for r in R if id(r) in B]
        sv = -sum(r["pnl"] for r in b)
        pool = [r["pnl"] for r in R]
        k = len(b)
        p = sum(1 for _ in range(2000) if -sum(random.sample(pool, k)) >= sv) / 2000 if k else 1.0
        # 6 h blocks
        ch = collections.defaultdict(float)
        for r in b: ch[int(r["t"] // (6 * 3.6e12))] -= r["pnl"]
        hp = sum(1 for v in ch.values() if v > 0.0005); hn = sum(1 for v in ch.values() if v < -0.0005)
        s += f" | {st} {k:3d} {sv:+5.2f} p={p:.3f} 6h+{hp}/-{hn}"
    print(s)
    return B
def exact(name, k, x):
    o = [v for v in raw.values()]
    for st in ("DEV", "VAL"):
        pass
    a = [v for v in o if v["ap"][k] >= x]; e = [v for v in o if v["ex"][k] >= x]
    sv = lambda L: -sum(v["pnl"] for v in L)
    dev = lambda L: [v for v in L if v["rk"] != "r42b"]; val = lambda L: [v for v in L if v["rk"] == "r42b"]
    print(f"  EXACT-vs-APPROX {name} on recorded fills: DEV approx {len(dev(a))}/{sv(dev(a)):+.2f} exact {len(dev(e))}/{sv(dev(e)):+.2f} | VAL(11-01 12:00-19:09) approx {len(val(a))}/{sv(val(a)):+.2f} exact {len(val(e))}/{sv(val(e)):+.2f}")
if __name__ == "__main__":
    g = lambda k, x: (lambda F, r: (F.get(k) or 0) >= x)
    for k, x in (("n_oth6", 3), ("samage", 20), ("samage", 25), ("sum_oth4", 25), ("sum_oth", 35), ("bundle", 30), ("sum_fresh", 35), ("risky_sum", 10)):
        rep(f"{k}>={x}", g(k, x))
        if k in ("n_oth6", "samage", "sum_oth4", "sum_oth"): exact(f"{k}>={x}", k, x)
    rep("creator ledger <=-0.1", lambda F, r: F["led_cr_pnl"] <= -0.1)
    rep("creator ledger <=-0.05", lambda F, r: F["led_cr_pnl"] <= -0.05)
    rep("breaker 2:0.2:10:30", seq=lambda: Brk(2, 0.2, 10, 30), need_ann=False)
    rep("breaker 1:0.15:10:30", seq=lambda: Brk(1, 0.15, 10, 30), need_ann=False)
