#!/usr/bin/env python3
# POST-MIGRATION STUDY: strategy search at OUR speed and cost. Rule chosen on R2, tested on R3, checked on R4.
# Families (triggers are causal: only information available at the trigger moment):
#   MIG   migration-moment snipe: trigger = the migration tx; guard vs the pool's open price
#   RIDE  fixed delay after migration (D s); optional filter on the price move since the end of the migration slot
#   DIP   a sell >= X SOL that moves the price <= -Y% (token age window, type)
#   DUMP1 the FIRST sell >= X SOL after migration with drop >= Y%
#   MOM   a buy >= X SOL that moves the price >= +Y%
#   DRAW  price <= (1-Y) x its high of the last W s (token age >= A), buy the drawdown
# Execution (pmsim): landing = trigger + LAT (35 / 50 ms), guard -> failed buy (-0.0005), size 0.5 SOL, exit timer
# (or TP/SL), pool fees per the pool's bps, +0.0035 SOL per round trip. One position at a time (greedy) and unconstrained.
import sys, os, json, itertools, time
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
import pmsim
from pmsim import Run, SMS, one_at_a_time, stats
OUT = pmsim.OUT
HOURS = {"R2": 21.8, "R3": 25.0}

def typ(t):
    if t["mayhem"]: return "mayhem"
    if t.get("age_s") is not None and t["age_s"] <= 1.0: return "instant"
    return "fast" if (t.get("age_s") or 1e9) < 300 else "slow"

TYPES = {"instant": ("instant",), "organic": ("fast", "slow"), "fast": ("fast",), "slow": ("slow",), "all": ("instant", "fast", "slow")}

class Ctx:
    def __init__(self, run):
        self.r = r = Run(run); R = r.R
        ng = len(r.gstart)
        self.gtype = np.array([typ(r.tok_of_grp[g]) if g in r.tok_of_grp else "?" for g in range(ng)])
        self.migarr = np.array([r.tok_of_grp[g]["mig_arr"] if g in r.tok_of_grp else 0.0 for g in range(ng)])
        self.migs = np.array([r.tok_of_grp[g]["mig_s"] if g in r.tok_of_grp else 0 for g in range(ng)])
        self.p0 = np.array([(r.tok_of_grp[g].get("p0_eff") or r.tok_of_grp[g]["p0"]) if g in r.tok_of_grp else 1.0 for g in range(ng)])
        self.age = (R["arr"] - self.migarr[r.rank]) / 1000
        self.drop = R["p_post"] / R["p_pre"] - 1
        self.sol = R["qtot"] / 1e9
        if run in HOURS: self.hours = HOURS[run]
        else: self.hours = (r.end_slot - min(t["mig_s"] for t in r.toks)) * SMS / 3.6e6
        # price at the end of the migration slot per group
        end0 = (self.migs + 1) * SMS
        B, Q, F, j = r.state_at(np.arange(ng), end0)
        self.p_end0 = Q / B

    def dedupe(self, idx, gap_ms):
        r = self.r; keep = []; last = {}
        for j, g, a in zip(idx.tolist(), r.rank[idx].tolist(), r.R["arr"][idx].tolist()):
            if g in last and a - last[g] < gap_ms: continue
            last[g] = a; keep.append(j)
        return np.array(keep, np.int64)

def evaluate(c, g, t, pref, P, lat):
    if len(g) == 0: return None
    kw = dict(size=P.get("size", 0.5), lat=lat, guard=P.get("guard"))
    if P.get("tp") or P.get("sl"): res = c.r.sim(g, t, pref, tp=P.get("tp"), sl=P.get("sl"), max_ms=P["hold"] * 1000, **kw)
    else: res = c.r.sim(g, t, pref, hold_ms=P["hold"] * 1000, **kw)
    ok = ~res["cens"]; res = {k: v[ok] for k, v in res.items()}
    if len(res["pnl"]) == 0: return None
    take = one_at_a_time(res)
    return dict(all=stats(res, hours=c.hours), one=stats(res, take, hours=c.hours))

def fam_mig(c, P):
    gs = np.nonzero(np.isin(c.gtype, TYPES[P["types"]]))[0]
    return gs, c.migarr[gs] + P.get("delay", 0) * 1000, c.p0[gs]

def fam_ride(c, P):
    gs = np.nonzero(np.isin(c.gtype, TYPES[P["types"]]))[0]
    t = c.migarr[gs] + P["delay"] * 1000
    B, Q, F, j = c.r.state_at(gs, t)
    p = Q / B; mv = p / c.p_end0[gs] - 1
    m = (mv >= P.get("mv0", -9)) & (mv <= P.get("mv1", 9))
    return gs[m], t[m], p[m]

def fam_event(c, P, side):
    R = c.r.R
    if side == -1: m = (R["side"] == -1) & (c.sol >= P["x"]) & (c.drop <= -P["y"])
    else: m = (R["side"] == 1) & (c.sol >= P["x"]) & (c.drop >= P["y"])
    m &= (c.age >= P["a0"]) & (c.age <= P["a1"]) & np.isin(c.gtype[c.r.rank], TYPES[P["types"]])
    idx = np.nonzero(m)[0]
    if P.get("first"):
        _, fi = np.unique(c.r.rank[idx], return_index=True); idx = idx[fi]
    else: idx = c.dedupe(idx, P["hold"] * 1000 + 500)
    return c.r.rank[idx], R["arr"][idx], R["p_post"][idx]

def rollmax(c, W):
    """rolling max of the post-trade price over the past W ms within each pool (monotonic deque, cached)"""
    if not hasattr(c, "_rm"): c._rm = {}
    if W in c._rm: return c._rm[W]
    import collections as _c
    R = c.r.R; pp = R["p_post"].tolist(); arr = R["arr"].tolist(); out = np.empty(len(pp))
    for g in range(len(c.r.gstart)):
        a, b = int(c.r.gstart[g]), int(c.r.gend[g]); dq = _c.deque()
        for j in range(a, b):
            while dq and pp[dq[-1]] <= pp[j]: dq.pop()
            dq.append(j)
            while arr[dq[0]] < arr[j] - W: dq.popleft()
            out[j] = pp[dq[0]]
    c._rm[W] = out
    return out

def fam_draw(c, P):
    R = c.r.R; r = c.r
    rm = rollmax(c, P["w"] * 1000)
    m = (R["side"] == -1) & (R["p_post"] <= (1 - P["y"]) * rm) & (c.age >= P["a0"]) & (c.age <= P["a1"]) & np.isin(c.gtype[r.rank], TYPES[P["types"]])
    idx = c.dedupe(np.nonzero(m)[0], P["hold"] * 1000 + 500)
    if len(idx) == 0: return idx, idx, idx
    return r.rank[idx], R["arr"][idx], R["p_post"][idx]

def grid(fam):
    if fam == "MIG":
        for ty, gd, h in itertools.product(["instant", "fast", "slow", "organic"], [1.05, 1.5, 100.0], [1, 3, 10, 30, 60, 180, 600]):
            yield dict(fam=fam, types=ty, guard=gd, hold=h)
    elif fam == "RIDE":
        for ty, d, (m0, m1), h in itertools.product(["instant", "fast", "slow"], [1, 5, 15, 30, 60, 120, 300],
                                                    [(-9, 9), (0, 9), (-9, 0), (0.05, 9), (-9, -0.1)], [30, 60, 120, 300, 600]):
            yield dict(fam=fam, types=ty, delay=d, mv0=m0, mv1=m1, hold=h, guard=1.05)
        for ty, d, tp, sl in itertools.product(["instant"], [5, 30, 60], [1.1, 1.2, 1.5], [0.85, 0.7]):
            yield dict(fam=fam, types=ty, delay=d, mv0=-9, mv1=9, hold=600, tp=tp, sl=sl, guard=1.05)
    elif fam in ("DIP", "DUMP1"):
        for x, y, (a0, a1), ty, h in itertools.product([0.5, 1, 2, 5, 10], [0.03, 0.06, 0.12, 0.25], [(0, 30), (0, 300), (30, 3600), (300, 86400)],
                                                        ["instant", "organic", "all"], [1.5, 3, 10, 30, 120]):
            if fam == "DUMP1" and a0 >= 300: continue
            yield dict(fam=fam, x=x, y=y, a0=a0, a1=a1, types=ty, hold=h, guard=1.03, first=(fam == "DUMP1"))
    elif fam == "MOM":
        for x, y, (a0, a1), ty, h in itertools.product([0.5, 1, 2, 5, 10], [0.02, 0.05, 0.1, 0.2], [(0, 30), (0, 300), (30, 3600), (300, 86400)],
                                                        ["instant", "organic", "all"], [1.5, 3, 10, 30, 120]):
            yield dict(fam=fam, x=x, y=y, a0=a0, a1=a1, types=ty, hold=h, guard=1.03)
    elif fam == "DRAW":
        for y, w, (a0, a1), ty, h in itertools.product([0.2, 0.35, 0.5], [10, 60, 300], [(30, 600), (600, 7200), (7200, 86400)],
                                                        ["instant", "organic"], [10, 60, 300]):
            yield dict(fam=fam, y=y, w=w, a0=a0, a1=a1, types=ty, hold=h, guard=1.03)

def trig(c, P):
    f = P["fam"]
    if f == "MIG": return fam_mig(c, P)
    if f == "RIDE": return fam_ride(c, P)
    if f in ("DIP", "DUMP1"): return fam_event(c, P, -1)
    if f == "MOM": return fam_event(c, P, 1)
    if f == "DRAW": return fam_draw(c, P)

if __name__ == "__main__":
    fams = sys.argv[1].split(",")
    t0 = time.time()
    c2 = Ctx("R2"); print("R2 ready", f"{time.time()-t0:.0f}s", flush=True)
    res = []; nvar = 0
    for fam in fams:
        for P in grid(fam):
            nvar += 1
            g, t, p = trig(c2, P)
            e = evaluate(c2, g, t, p, P, 35.0)
            if e is None: continue
            res.append(dict(P=P, R2_35=e))
        print(fam, "variants so far", nvar, f"{time.time()-t0:.0f}s", flush=True)
    # choose on R2: one-at-a-time pnl, at least 30 trades, positive without the top 1%
    ok = [x for x in res if x["R2_35"]["one"]["n"] >= 30 and x["R2_35"]["one"]["ex_top1pct"] > 0 and x["R2_35"]["one"]["pnl"] > 0]
    ok.sort(key=lambda x: -x["R2_35"]["one"]["pnl"])
    top = ok[:15]
    print(f"{'/'.join(fams)}: {nvar} variants, {len(res)} with trades, {len(ok)} positive on R2 (n>=30, ex-top1% > 0)", flush=True)
    del c2
    c3 = Ctx("R3"); c4 = Ctx("R4")
    for x in top:
        P = x["P"]
        for nm, c in (("R3", c3), ("R4", c4)):
            g, t, p = trig(c, P)
            x[f"{nm}_35"] = evaluate(c, g, t, p, P, 35.0)
            x[f"{nm}_50"] = evaluate(c, g, t, p, P, 50.0)
    json.dump(dict(nvar=nvar, n_trades=len(res), n_pos=len(ok), all=res, top=top), open(f"{OUT}/search_{'_'.join(fams)}.json", "w"))
    for x in top:
        f = lambda e, k="one": {kk: e[k][kk] for kk in ("n", "pnl", "mean", "win", "ex_top1pct", "per_day") if kk in e[k]} if e else None
        print(json.dumps(x["P"]), "\n   R2:", f(x["R2_35"]), "\n   R3@35:", f(x.get("R3_35")), " R3@50:", f(x.get("R3_50")), "\n   R4@35:", f(x.get("R4_35")), flush=True)
