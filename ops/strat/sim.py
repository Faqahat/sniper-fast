# Offline simulation library for /root/strat (paper only).
import json, bisect, collections, math
SLOT = 0.2165
CK = [69, 139, 277, 416, 554, 831, 1109]
PRIO = 0.0003 + 0.000005
DS_W = 30.25   # ds uniform sample: 1 per 30.25 creates
def load(path="/root/strat/pipe.jsonl"):
    R = []
    seen = set()
    for l in open(path):
        try: x = json.loads(l)
        except Exception: continue
        if x["mint"] in seen: continue
        seen.add(x["mint"]); R.append(x)
    return R
class Tok:
    __slots__ = ("x", "ds", "vs", "vt", "fee", "okd", "devd", "v0", "S", "bt", "src", "ck")
    def __init__(self, x):
        self.x = x; self.S = x["slot"]; self.bt = x["bt"]; self.src = x["src"]
        ds, vs, vt, fee = [], [], [], []
        for r in x.get("rows") or []:
            if not r[1]: continue
            e = r[1][-1]
            ds.append(r[0]); vs.append(e[4]); vt.append(e[5])
            f = ((e[6] or 95) + (e[7] or 30)) / 1e4
            fee.append(f)
        self.ds, self.vs, self.vt, self.fee = ds, vs, vt, fee
        self.okd = []
        for d, n in x.get("act") or []:
            self.okd += [d] * n
        self.devd = [d for d in (x.get("dev_txs") or []) if d >= 1]
        self.v0 = x.get("v0")
        self.ck = {c[0]: c[1] for c in (x.get("cks") or [])}
    def st(self, d):
        i = bisect.bisect_right(self.ds, d) - 1
        if i < 0: return None
        return i
    def n_upto(self, d): return bisect.bisect_right(self.okd, d)
def buy(vs, vt, X, f):
    a = X / (1 + f)
    return vt * a / (vs + a)
def sell(vs, vt, q, f):
    return vs * q / (vt + q) * (1 - f)
def trade(t, dk, X, exitspec, lat=2, shift=False):
    """entry at state after slot dk+lat; returns (pnl_sol, hold_s, exit_reason) or None."""
    i0 = t.st(dk + lat)
    if i0 is None: return None
    vs, vt, f = t.vs[i0], t.vt[i0], t.fee[i0]
    q = buy(vs, vt, X * 1e9, f)
    p0 = vs / vt
    kind = exitspec[0]
    d0 = dk + lat
    a = X * 1e9 / (1 + f)
    def out(i, reason):
        if shift:   # our buy stays in the curve: exit state = historical vsol + a (k of the historical state)
            Vs = t.vs[i] + a; Vt = t.vs[i] * t.vt[i] / Vs
            g = sell(Vs, Vt, q, t.fee[i]) / 1e9
        else:
            g = sell(t.vs[i], t.vt[i], q, t.fee[i]) / 1e9
        return g - X - 2 * PRIO, (t.ds[i] - d0) * SLOT if t.ds[i] > d0 else 0.0, reason
    if kind == "time":
        H = int(exitspec[1] / SLOT)
        i = t.st(d0 + H + lat)
        return out(i, "time")
    # path-dependent: iterate rows after entry
    H = int(exitspec[-1] / SLOT)
    pmax = p0
    j = i0 + 1
    n = len(t.ds)
    while j < n and t.ds[j] <= d0 + H:
        p = t.vs[j] / t.vt[j]
        trig = False
        if kind == "trail":
            pmax = max(pmax, p)
            if p < (1 - exitspec[1]) * pmax: trig = True
        elif kind == "tpsl":
            if p >= exitspec[1] * p0 or p <= exitspec[2] * p0: trig = True
        elif kind == "trailtp":   # trailing stop that only arms after +arm
            pmax = max(pmax, p)
            if pmax >= exitspec[2] * p0 and p < (1 - exitspec[1]) * pmax: trig = True
            if p <= exitspec[3] * p0: trig = True
        if trig:
            # execute at the next observed state at or after d+lat (conservative)
            dj = t.ds[j]
            if t.n_upto(dj + lat) == t.n_upto(dj):
                return out(j, "trig")       # no tx in (dj, dj+lat]: state unchanged
            k = j
            while k + 1 < n and t.ds[k] < dj + lat:
                k += 1
            return out(k, "trig")
        j += 1
    i = t.st(d0 + H + lat)
    return out(i, "time")
EXITS = [("time", 10), ("time", 20), ("time", 30), ("time", 60), ("time", 120), ("time", 180), ("time", 300),
         ("trail", 0.15, 120), ("trail", 0.25, 120), ("trail", 0.25, 300), ("trail", 0.35, 300),
         ("tpsl", 1.3, 0.8, 120), ("tpsl", 1.5, 0.8, 300), ("tpsl", 1.5, 0.7, 300), ("tpsl", 2.0, 0.7, 300),
         ("trailtp", 0.2, 1.3, 0.75, 300), ("trailtp", 0.3, 1.5, 0.7, 300)]
def feats(t, dk):
    v = t.ck.get(dk)
    if not v: return None
    v /= 1e9; v0 = t.v0 / 1e9
    prev = [c for c in CK if c < dk and t.ck.get(c)]
    vprev = t.ck[prev[-1]] / 1e9 if prev else v0
    vmax = max([v0, v] + [t.ck[c] / 1e9 for c in prev])
    n = t.n_upto(dk)
    n15 = n - t.n_upto(dk - 69)
    n5 = n - t.n_upto(dk - 23)
    i = n - 1
    gap = (dk - t.okd[i]) * SLOT if i >= 0 else 999
    dsell = sum(1 for d in t.devd if d <= dk)
    nerr = sum(c for d, c in (t.x.get("err_act") or []) if d <= dk)
    return dict(T=round(dk * SLOT), v=v, v0=v0, dev=v0 - 30, dv=v - vprev, vmax=vmax, dd=v / vmax, n=n, n15=n15, n5=n5,
                gap=gap, dsell=dsell, nerr=nerr, m=(v / v0) ** 2)
