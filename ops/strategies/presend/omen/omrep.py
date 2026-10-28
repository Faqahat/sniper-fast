#!/usr/bin/env python3
"""OMEN tables lib (INFERRED). Costs MEASURED (SLIPPAGE.md): 2.015 mSOL per fill (buy fee+tip+ATA rent, sell fee+tips, rent back),
5,120 lamports per landed failed try."""
import sys, pickle, collections
import numpy as np
sys.path.insert(0, "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/rearm2/code")
import rep
W = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/omen"
NAME = {2: "10-24", 3: "10-25", 4: "10-26", 5: "10-27", 6: "10-28"}
TRIP = 2_015_141; FF = 5120; K65 = (650_000_000, 0.2, 0.0); K65c = (650_000_000, 0.2, 0.2)


class Day:
    def __init__(self, D, tag):
        Z = pickle.load(open(f"{W}/res_D{D}_{tag}.pkl", "rb"))
        self.D = D; self.meta = Z["meta"]; self.out = Z["out"]; self.hrs = rep.day_hours(D); self.H = sorted(self.hrs)
        self.hours = sum(self.hrs.values()); self.draws = sorted(self.out["base"])

    def ok(self, r): return (r["bt"] // 3600) * 3600 in self.hrs

    def per_hour(self, scen, d, key=K65, only=None, drop_top=0):
        rows = self.out[scen][d]["rows"]; v = collections.defaultdict(float)
        sel = lambda r: only is None or r["tag"] in only
        ids_ = set()
        if drop_top:
            fills = sorted((r for r in rows if r.get("filled") and sel(r) and self.ok(r)), key=lambda r: -r["grid"][key])[:drop_top]
            ids_ = {id(r) for r in fills}
        for r in rows:
            if not r["armed"] or not sel(r) or not self.ok(r): continue
            h = (r["bt"] // 3600) * 3600
            v[h] -= r["nfail"] * FF
            if r.get("filled") and id(r) not in ids_: v[h] += r["grid"][key] - TRIP
        return v


def boot(days, f, n=2000, seed=7):
    rng = np.random.default_rng(seed); cells = []
    for dy in days:
        V = [f(dy, d) for d in dy.draws]
        for h in dy.H: cells.append((dy.hrs[h], np.array([v.get(h, 0.0) for v in V])))
    w = np.array([c[0] for c in cells]); M = np.stack([c[1] for c in cells])
    mean = M.mean(axis=1).sum() / w.sum() * 24 / 1e9
    nd = M.shape[1]; res = np.empty(n)
    for b in range(n):
        ix = rng.integers(len(cells), size=len(cells)); dj = rng.integers(nd, size=len(cells))
        res[b] = M[ix, dj].sum() / w[ix].sum() * 24 / 1e9
    return mean, np.percentile(res, 5), np.percentile(res, 95)


def fmt(m, lo, hi): return f"{m:+.2f} [{lo:+.2f}, {hi:+.2f}]"


def delta_fn(v, key=K65, drop_top=0, only=None):
    def f(dy, d):
        a = dy.per_hour(v, d, key, drop_top=drop_top, only=only); b = dy.per_hour("base", d, key)
        return {h: a.get(h, 0) - b.get(h, 0) for h in set(a) | set(b)}
    return f


def lvl_fn(v, key=K65, only=None, drop_top=0): return lambda dy, d: dy.per_hour(v, d, key, only=only, drop_top=drop_top)


def counts(dy, v):
    A = []; T = []; F = []; FA = []; AA = []; S = []
    for d in dy.draws:
        rows = [r for r in dy.out[v][d]["rows"] if dy.ok(r)]
        A.append(sum(r["armed"] for r in rows)); T.append(sum(r.get("sent", 0) for r in rows if r["armed"]))
        F.append(sum(1 for r in rows if r.get("filled"))); FA.append(sum(1 for r in rows if r.get("filled") and r["tag"] == "add"))
        AA.append(sum(1 for r in rows if r["armed"] and r["tag"] == "add"))
    k = 24 / dy.hours
    return dict(arms=np.mean(A) * k, tries=np.mean(T) * k, fills=np.mean(F) * k, fills_add=np.mean(FA) * k, arms_add=np.mean(AA) * k)


def rate_stats(dy, v):
    a = []; capb = []; refs = []
    for d in dy.draws:
        s = dy.out[v][d]["sent"]; r = dy.out[v][d]["refused"]
        tot = sum(s.values()); rf = sum(r.values()); secs = set(s) | set(r)
        a.append(tot / (dy.hours * 3600)); capb.append(sum(1 for x in secs if r.get(x, 0) > 0) / max(len(secs), 1)); refs.append(rf / max(tot + rf, 1))
    return np.mean(a), np.mean(capb), np.mean(refs)
