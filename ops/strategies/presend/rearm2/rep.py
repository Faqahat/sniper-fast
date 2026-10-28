#!/usr/bin/env python3
"""REARM2 tables from res_D<k>_main.pkl (INFERRED)."""
import sys, json, pickle, collections, math
import numpy as np
W = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/rearm2"
DAY0 = 1793038500 - 5 * 86400
NAME = {2: "10-24", 3: "10-25", 4: "10-26", 5: "10-27", 6: "10-28", 7: "10-29"}
TRAIN = (2, 3, 4); TEST = (5, 6, 7)
TRIP = 2_900_000
END = int(open(f"{W}/end_bt.txt").read())


def gap_msol(s):
    """live-fill size correction (PAPER_VS_LIVE §4): gap per SOL 15.2 @0.35, 21.5 @0.55, 27.0 @0.75 (linear between, extrapolated)"""
    xs = (0.35, 0.55, 0.75); ys = (15.2, 21.5, 27.0)
    if s <= 0.55: r = ys[0] + (ys[1] - ys[0]) * (s - 0.35) / 0.2
    else: r = ys[1] + (ys[2] - ys[1]) * (s - 0.55) / 0.2
    return r * s


def day_hours(D):
    hj = "/home/moiz/sniper-data/dv8/hours.json" if D <= 5 else f"{W}/hoursN.json"
    good = {r["h"] for r in json.load(open(hj))["rows"] if r["usable"]}
    a = DAY0 + D * 86400; b = min(a + 86400, END)
    hrs = {}
    for h in range((a // 3600) * 3600, b, 3600):
        if h in good or (h == (END // 3600) * 3600 and D == 7):
            ov = min(h + 3600, b) - max(h, a)
            if ov > 0: hrs[h] = ov / 3600
    return hrs


class Day:
    def __init__(self, D, tag="main"):
        Z = pickle.load(open(f"{W}/res_D{D}_{tag}.pkl", "rb"))
        self.D = D; self.meta = Z["meta"]; self.out = Z["out"]; self.hrs = day_hours(D); self.H = sorted(self.hrs)
        self.hours = sum(self.hrs.values()); self.draws = sorted(self.out["base"])

    def hour_of(self, bt):
        return (bt // 3600) * 3600

    def per_hour(self, scen, d, size=650_000_000, tp=0.2, cut=0.0, failfee=5000, only=None, drop_top=0):
        """-> dict hour -> net lamports (fills: grid gross - trip cost; every landed failed try: failfee)"""
        rows = self.out[scen][d]["rows"]
        v = collections.defaultdict(float)
        fills = [r for r in rows if r.get("filled") and (only is None or r["kind"] == only)]
        if drop_top:
            top = sorted((r for r in fills if r["kind"] == "re"), key=lambda r: -r["grid"][(size, tp, cut)])[:drop_top]
            ids_ = {id(r) for r in top}
        else: ids_ = set()
        for r in rows:
            if not r["armed"] or (only is not None and r["kind"] != only): continue
            h = self.hour_of(r["bt"])
            if h not in self.hrs: continue
            v[h] -= r["nfail"] * failfee
            if r.get("filled") and id(r) not in ids_: v[h] += r["grid"][(size, tp, cut)] - TRIP
        return v


def boot(days, f, n=2000, seed=7):
    """f(day, draw) -> dict hour -> value (lamports); returns mean SOL/day and 90% CI resampling hours (and draws)"""
    rng = np.random.default_rng(seed)
    cells = []      # (hours weight, [values per draw])
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
