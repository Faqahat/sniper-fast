"""PAPER AUDIT library: a line-by-line Python port of the engine's pre-send SHADOW (src/presend.rs: the T2 window, the queue rows'
fill search, the post-fill path with the follower-drop model, the 2-slot exit) run on the decoded recorder tape, so a shadow window
can be re-scored (a) exactly as the engine did (validation against its presend_fill / presend_exit records), (b) without our own
live trades in the tape, (c) at another size, (d) at another landing delay D, (e) with another exit.

Tape: /home/moiz/sniper-data/paper_audit/tab (pa_decode.py + real/build.py over the recorder chunks of the run; per trade the sha256
key `sh` of the follower-slack table). Clock = the engine's block-position clock: a = slot x 212 + idx / max(400, idx + 1) x 212 ms.
"""
import json, math, re, bisect
import numpy as np

SMS = 212.0
UNTRADE_V = 100e9
GRADV = 110e9
SELL_LAT = 75.0
WHALE_SELL_MS = 30.0
WMAX_SLOTS = 250.0
HMAX = 40
ROWS = {"a": 0.0, "b": 5.0, "c": 10.0}
OURS = ("EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE")
import os
TAB = os.environ.get("PA_TAB", "/home/moiz/sniper-data/paper_audit/tab")   # PA_TAB = another run's tape


def _slack_table():
    src = open("/home/moiz/sniper/src/presend.rs").read()
    body = src[src.index("const SLACK: [f64; 711] = [") + len("const SLACK: [f64; 711] = ["):]
    body = body[:body.index("];")]
    v = [float(x) for x in re.findall(r"[-+]?\d[\d.e+-]*", body)]
    assert len(v) == 711, len(v)
    return np.array(v)


SLACK = _slack_table()


def f32(x): return float(np.float32(x))


def slack_of(sh):
    """presend.rs slack_of_sig from the stored sha256 prefix"""
    x = sh / 4294967296.0
    k = min(int(x * 711), 710)
    return f32(min(SLACK[k], 1e6))


def fee_rate(fbps, cbps): return f32(((fbps if fbps else 95) + (cbps if cbps else 30)) / 1e4)


def arrival(s, i):
    size = max(400, i + 1)
    return s * SMS + (i / size) * SMS


def py_floordiv(a, b): return a // b


class Tape:
    """the decoded run tape, indexed by mint"""
    def __init__(self, tab=TAB):
        self.T = np.load(f"{tab}/trades.npy")
        self.ids = json.load(open(f"{tab}/ids.json"))
        self.gid = {k: i for i, k in enumerate(self.ids)}
        S = np.load(f"{tab}/slots.npy")
        self.maxi = dict(zip(S["slot"].tolist(), S["maxi"].tolist()))
        self.s_lo, self.s_hi = int(S["slot"][0]), int(S["slot"][-1])
        mm = self.T["mint"]
        self.order = np.argsort(mm, kind="stable")
        self.ms = mm[self.order]
        self.ours = {self.gid[w] for w in OURS if w in self.gid}

    def trades(self, mint, s_max=None):
        """the mint's trades in chain order (numpy records), optionally up to slot s_max"""
        g = self.gid.get(mint)
        if g is None: return None
        a, b = np.searchsorted(self.ms, g), np.searchsorted(self.ms, g, side="right")
        t = self.T[np.sort(self.order[a:b])]
        if s_max is not None: t = t[t["slot"] <= s_max]
        return t


class Rec:
    __slots__ = ("s", "i", "j", "a", "p", "refp", "buy", "sol", "tok", "vsol", "vtok", "fr", "u", "sh", "ours")


def build_recs(t, ours_ids, drop_ours=False):
    """the shadow's per-token tape: arrival, post-trade price, trailing reference (presend.rs trade())"""
    out = []
    p_first = None
    rp = None
    for x in t:
        u = int(x["user"])
        is_ours = u in ours_ids
        if drop_ours and is_ours: continue
        r = Rec()
        r.s, r.i, r.j = int(x["slot"]), int(x["idx"]), int(x["j"])
        r.buy = bool(x["buy"]); r.sol, r.tok, r.vsol, r.vtok = int(x["sol"]), int(x["tok"]), int(x["vsol"]), int(x["vtok"])
        r.fr = fee_rate(int(x["fee_bps"]), int(x["cfee_bps"])); r.u = u; r.sh = int(x["sh"]); r.ours = is_ours
        vf, tf, sf, kf = float(r.vsol), float(r.vtok), float(r.sol), float(r.tok)
        if p_first is None:
            vp, tp = (vf - sf, tf + kf) if r.buy else (vf + sf, tf - kf)
            p_first = vp / max(tp, 1.0)
        r.a = arrival(r.s, r.i)
        k = len(out)
        while True:
            c = 0 if rp is None else rp + 1
            if c >= k or out[c].a > r.a - 50.0: break
            rp = c
        r.refp = out[rp].p if rp is not None else p_first
        r.p = vf / tf
        out.append(r)
    return out


class Path:
    """presend.rs Path (one buy right after trade m, landing at a_land)"""
    def __init__(self, m, m_idx, a_land, size, slip, tp, sl):
        fr0 = m.fr; vb = float(m.vsol); tb = float(m.vtok)
        self.ok = vb < UNTRADE_V
        if not self.ok: return
        x = size * 1e9 / (1.0 + fr0); q = tb * x / (vb + x)
        self.slip, self.size, self.tp, self.sl = slip, size, tp, sl
        self.q, self.v, self.t = q, vb + x, tb - q
        s_land = int(py_floordiv(a_land, SMS)); self.s_in = max(m.s, s_land)
        self.frs = fr0
        self.cur = self.v * q / (self.t + q) * (1.0 - self.frs) / 1e9 - size
        self.p_ref = vb / tb; self.rmin = 1e9
        self.poff, self.pmn = [], []
        self.ftp = self.fsl = None
        self.stop = self.grad = False
        self.next = m_idx + 1; self.last_s = None
        self.dropped = 0; self.followers = 0
        self.entry = (vb, tb, x, q)

    def feed(self, r):
        if self.stop: return
        sj = r.s; pos = r.a - sj * SMS
        kj = 2 * sj + (1 if pos >= SELL_LAT else 0)
        while len(self.poff) <= HMAX + 1 and 2 * (self.s_in + len(self.poff)) + 1 <= kj:
            self.poff.append(self.cur); self.pmn.append(self.rmin)
        if sj > self.s_in + HMAX + 1 or len(self.poff) > HMAX + 1: self.stop = True; return
        applied = True
        if r.buy:
            sol = float(r.sol); dt = self.t * sol / (self.v + sol)
            self.followers += 1
            if self.slip and dt < float(r.tok) / (1.0 + slack_of(r.sh)): applied = False; self.dropped += 1
            else: self.v += sol; self.t -= dt
        else:
            tk = float(r.tok); so = self.v * tk / (self.t + tk); self.v -= so; self.t += tk
        if applied: self.frs = r.fr
        self.cur = self.v * self.q / (self.t + self.q) * (1.0 - self.frs) / 1e9 - self.size
        self.last_s = sj
        if self.v >= GRADV: self.stop = True; self.grad = True; return
        if applied:
            pr = (self.v / self.t) / self.p_ref
            if pr < self.rmin: self.rmin = pr
            val = (self.cur + self.size) / self.size
            if self.tp > 0 and self.ftp is None and val >= 1.0 + self.tp: self.ftp = sj
            if self.sl > 0 and self.fsl is None and val <= 1.0 - self.sl: self.fsl = sj

    def exit(self, c):
        """the final exit with every trade fed (offline: h = infinity)"""
        co = self.s_in + c
        a = self.ftp if (self.ftp is not None and self.ftp + 1 < co) else None
        b = self.fsl if (self.fsl is not None and self.fsl + 1 < co) else None
        trig = None if (a is None and b is None) else (a if b is None else (b if a is None else min(a, b)))
        so = co if trig is None else trig + 1
        dd = so - self.s_in
        val = self.poff[dd] if len(self.poff) > dd else self.cur
        why = "time"
        if a is not None and b is not None: why = "tp_sl" if a == b else ("tp" if a < b else "sl")
        elif a is not None: why = "tp"
        elif b is not None: why = "sl"
        return {"so": so, "dd": dd, "val": val, "why": why}


def run_path(recs, m_idx, a_land, size, slip, tp, sl, c=2):
    P = Path(recs[m_idx], m_idx, a_land, size, slip, tp, sl)
    if not P.ok: return None, None
    for k in range(m_idx + 1, len(recs)):
        P.feed(recs[k])
        if P.stop: break
    return P, P.exit(c)


def find_trig(recs, s, i, j):
    for k, r in enumerate(recs):
        if (r.s, r.i, r.j) == (s, i, j): return k
    return None


def window_fill(recs, jt, whale_u, D, drop=0.12, live_ms=50.0, window_slots=10):
    """one row of one window (presend.rs step_row, offline): the fill (x, m, a_land, ft) or the reason there is none"""
    trig = recs[jt]
    st = trig.a + live_ms
    en0 = st + window_slots * SMS
    enl0 = trig.a + live_ms + WMAX_SLOTS * SMS
    je = next((r.a for r in recs[jt + 1:] if (not r.buy) and r.u == whale_u), None)
    en = min(je + WHALE_SELL_MS, en0) if je is not None else en0
    enl = min(je + WHALE_SELL_MS, enl0) if je is not None else enl0
    nxt = jt + 1; n = len(recs)
    while True:
        if nxt >= n: return {"fill": False, "hit": None, "en": en, "st": st}
        x = recs[nxt]
        if x.a < st: nxt += 1; continue
        if x.a >= en: return {"fill": False, "hit": None, "en": en, "st": st}
        if not (x.p / x.refp <= 1.0 - drop): nxt += 1; continue
        a_land = x.a + D
        if a_land >= enl: return {"fill": False, "hit": None, "en": en, "st": st}
        m = nxt
        while m + 1 < n and recs[m + 1].a <= a_land: m += 1
        lim = x.refp * (1.0 - drop)
        if not (recs[m].p <= lim): nxt += 1; continue
        if float(recs[m].vsol) >= UNTRADE_V: return {"fill": False, "hit": "untradeable", "en": en, "st": st}
        ft = x.a + f32(a_land - x.a)
        if not (ft < en): return {"fill": False, "hit": "late", "en": en, "st": st, "x": nxt}
        return {"fill": True, "x": nxt, "m": m, "a_land": a_land, "ft": ft, "en": en, "st": st, "lim": lim}


def cc_of(maxi, s, i):
    """the real block-position clock (custom37): slot x 212 + (idx + 0.5) / (max idx of the slot + 1) x 212"""
    return s * SMS + (i + 0.5) / (maxi.get(s, 400) + 1.0) * SMS


def last_before(recs, key):
    """index of the last trade with (slot, idx, j) < key (None: none)"""
    lo = None
    for k, r in enumerate(recs):
        if (r.s, r.i, r.j) < key: lo = k
        else: break
    return lo


def value_at(recs, m_idx, size, slip, stop, maxi=None, by_cc=False):
    """our buy right after trade m_idx, sold right before `stop`: a (slot, idx) position, or a real-clock time (by_cc) -> gross SOL
    (SOL back after pump's fee - size), followers seen / dropped. No TP / SL (the 20% ones rarely fire inside 0.5 s)"""
    m = recs[m_idx]
    vb, tb, fr0 = float(m.vsol), float(m.vtok), m.fr
    if vb >= UNTRADE_V: return None
    x = size * 1e9 / (1.0 + fr0); q = tb * x / (vb + x)
    v, t, frs = vb + x, tb - q, fr0
    nf = nd = 0
    for r in recs[m_idx + 1:]:
        if by_cc:
            if cc_of(maxi, r.s, r.i) >= stop: break
        elif (r.s, r.i) >= stop: break
        if r.buy:
            sol = float(r.sol); dt = t * sol / (v + sol); nf += 1
            if slip and dt < float(r.tok) / (1.0 + slack_of(r.sh)): nd += 1; continue
            v += sol; t -= dt
        else:
            tk = float(r.tok); so = v * tk / (t + tk); v -= so; t += tk
        frs = r.fr
        if v >= GRADV: break
    return {"gross": v * q / (t + q) * (1.0 - frs) / 1e9 - size, "followers": nf, "dropped": nd}
