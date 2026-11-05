"""T2-WINDOWS scorer library: load e4 sims, money per candidate x mechanics, periods, hours, one-position overlap, stats.
Money of a simulated window [ESTIMATE] = expected curve P&L (filled share x curve P&L at the exit H) + filled share x fixed costs
(run's median live realized - live curve P&L, scaled 2.5 % per SOL of size) - landed non-filling tries x 5,120 lamports."""
import sys, glob, pickle, collections, statistics, bisect
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/t2windows")
import t2lib as L

PKT = 5 * 3600
FIT_RUNS, CHOOSE_RUNS, FINAL_RUNS = (39, 40, 41, 42), (42, 44, 45, 46), (47, 48, 49)


def period(run, t_ns):
    if run in (39, 40, 41): return "fit"
    if run == 42: return "fit" if t_ns / 1e9 < L.CUT else "choose"
    if run in (44, 45, 46): return "choose"
    if run in (47, 48, 49): return "final"
    return "other"


def load(simdir=None):
    import os
    simdir = simdir or os.environ.get("T2W_SIMDIR", "sim")
    X = []
    for fn in sorted(glob.glob(f"{L.D}/{simdir}/b*.pkl")): X += pickle.load(open(fn, "rb"))
    P = pickle.load(open(f"{L.D}/prep.pkl", "rb"))
    for x in X: x["per"] = period(x["run"], x["anc"]["t"])
    return X, P


def fixed(P, run, kind, spend):
    c = P["cal"][run]; k = "rearm" if kind == "re" else "t2"
    f = c["fixed"].get(k) or -17e6; fs = c["fixed_spend"].get(k) or spend
    return f - 0.025 * (spend - fs)


def money(x, P, mech, hj=0, fees=True, spend=None):
    s = x["sims"][mech]
    if s.get("noarm"): return 0.0, 0.0
    sp = spend or {"m0": None}.get(mech)
    if sp is None:
        c = P["cal"][x["run"]]
        sp = {"s30": 3e8, "s45": 4.5e8, "s65": 6.5e8, "h0s45": 4.5e8, "h3s45": 4.5e8, "cur": 5.5e8}.get(mech) or (c["re_spend"] if x["c"] == "re" else c["spend"])
    v = s[f"c{hj}"] + s["p"] * fixed(P, x["run"], x["c"], sp)
    if fees: v -= s["fails"] * L.FAIL
    return v / 1e9, s["p"]


def coverage(P):
    """tape-covered live hours per segment: run span (first -> last record) intersected with the tape (slots in maxi, by 5-min file spans)"""
    import os
    spans = []
    for rec in sorted(glob.glob(f"{L.D}/raw/*/")):
        for fn in os.listdir(rec):
            if fn.endswith(".jsonl") and not fn.endswith(".bots.jsonl"):
                t0 = int(fn.split("_")[1].split(".")[0]); spans.append((t0, t0 + 300))
    spans.sort(); merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1] + 5: merged[-1][1] = max(merged[-1][1], b)
        else: merged.append([a, b])
    return merged


def covered_hours(merged, lo, hi):
    h = 0.0
    for a, b in merged:
        x, y = max(a, lo), min(b, hi)
        if y > x: h += y - x
    return h / 3600


def seg_hours(P, merged):
    """hours per (run, period) of live run time covered by the tape"""
    out = {}
    for r, c in P["cal"].items():
        lo, hi = c["t_first"] / 1e9, c["t_last"] / 1e9
        if r == 42:
            out[(r, "fit")] = covered_hours(merged, lo, L.CUT); out[(r, "choose")] = covered_hours(merged, L.CUT, hi)
        else:
            out[(r, period(r, c["t_first"]))] = covered_hours(merged, lo, hi)
    return out


def st(v, hrs=None):
    v = list(v)
    if not v: return {"n": 0, "sum": 0.0, "win": None, "wo5": 0.0, "day": 0.0 if hrs else None}
    s = sorted(v)
    o = {"n": len(v), "sum": round(sum(v), 3), "win": round(sum(1 for x in v if x > 0) / len(v), 3), "wo5": round(sum(s[:-5]), 3)}
    o["day"] = round(sum(v) / hrs * 24, 2) if hrs else None
    return o


class Positions:
    """the one-position rule: live positions (fill -> sell land + 300 ms) + windows armed per mint; added positions are inserted greedily"""
    def __init__(self, P):
        self.iv = sorted((a[4], a[5], a[6], a[3]) for a in P["live_pos"])     # (t0, t1, pnl, mint)
        self.t0 = [x[0] for x in self.iv]
        self.arm = collections.defaultdict(list)
        for r, ses, w, m, t0, t1, kind in P["live_arm"]: self.arm[m].append((t0, t1))
        self.added = []

    def busy(self, t):
        k = bisect.bisect_right(self.t0, t) - 1
        while k >= 0 and k > bisect.bisect_right(self.t0, t) - 6:
            if self.iv[k][0] <= t <= self.iv[k][1]: return True
            k -= 1
        for a, b in self.added:
            if a <= t <= b: return True
        return False

    def mint_armed(self, m, t0, t1):
        return any(a <= t1 and t0 <= b for a, b in self.arm.get(m, ()))

    def displaced(self, t0, t1):
        """live fills that land inside an added position's span: their realized P&L is lost"""
        k = bisect.bisect_left(self.t0, t0); out = []
        while k < len(self.iv) and self.iv[k][0] <= t1: out.append(self.iv[k][2]); k += 1
        return out
