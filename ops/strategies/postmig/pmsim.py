#!/usr/bin/env python3
# POST-MIGRATION STUDY: replay engine for PumpSwap entries at OUR speed and costs (library).
#  - state at a time t in a pool = pre-trade state (B, Qv) of the first recorded trade arriving at or after t (post-trade
#    state of the last trade when none follows). arrival(tx) = slot*212 + index/blocksize*212 ms.
#  - entry: trigger arrival + LAT (35 / 50 ms). Trades arriving before that are ahead of us. Guard: pool price at our
#    landing > GUARD x reference price (price right after the trigger; the open price for migration snipes) -> failed
#    buy, -0.0005 SOL.
#  - buy X SOL: e = X*1e4/(1e4+F); out = B*e/(Qv+e) (F = the pool's lp+protocol+creator bps of the neighbouring trade).
#  - exit: decision time (timer / TP / SL / event) + LAT; sell all: q = Qv*out/(B+out); proceeds = q*(1-F/1e4).
#  - "independent legs": our own buy's impact is not carried to the exit state (conservative by ~our impact, <1% at
#    0.5 SOL in a >=85 SOL pool); followers' slippage failures are not modelled here (exact replay in pmexact).
#  - costs: +0.0035 SOL per round trip (tips + priority), failed buy 0.0005.
import os, json, pickle
import numpy as np
OUT = "/home/moiz/sniper-data/strategies/postmig"
SMS = 212.0; FIX = 0.0035; FAIL = 0.0005
RUNS = ("R2", "R3", "R4")

class Run:
    def __init__(self, run, mayhem_ok=False):
        self.run = run
        R = dict(np.load(os.path.join(OUT, f"{run}_rows.npz")))
        self.toks = [json.loads(l) for l in open(os.path.join(OUT, f"{run}_tokens.jsonl"))]
        st = pickle.load(open(os.path.join(OUT, f"{run}_strs.pkl"), "rb")); self.strs = st["strs"]; self.sigs = st["sigs"]
        gid = {x: j for j, x in enumerate(self.strs)}
        S = dict(np.load(os.path.join(OUT, f"{run}_slots.npz"))); self.end_slot = int(S["s"].max()); self.bs = dict(zip(S["s"].tolist(), S["bs"].tolist()))
        self.slot_bt = dict(zip(S["s"].tolist(), S["bt"].tolist()))
        self.R = R
        n = len(R["s"]); m = R["mint"]
        st_ = np.r_[0, np.nonzero(np.diff(m))[0] + 1]; en = np.r_[st_[1:], n]
        self.gstart = st_; self.gend = en
        self.grp_of_mint = {int(m[a]): g for g, a in enumerate(st_.tolist())}
        self.rank = np.repeat(np.arange(len(st_)), en - st_)
        self.key = self.rank.astype(np.int64) * 10**13 + np.round(R["arr"] * 100).astype(np.int64)
        B = R["B"].astype(np.float64); Qv = R["Qv"]; base = R["base"].astype(np.float64); qc = R["qcurve"].astype(np.float64)
        lp = R["lpb"] / 1e4; buy = R["side"] == 1
        self.B = B; self.Qv = Qv
        self.Bp = np.where(buy, B - base, B + base)
        self.Qp = np.where(buy, Qv + qc + np.ceil(qc * lp), Qv - qc + np.ceil(qc * lp))
        self.F = R["F"].astype(np.float64)
        self.end_arr = self.end_slot * SMS
        # token table by group
        self.tok_of_grp = {}
        for t in self.toks:
            g = self.grp_of_mint.get(gid.get(t["mint"], -1))
            if g is not None:
                t["grp"] = g; self.tok_of_grp[g] = t
                bsz = self.bs.get(t["mig_s"], 400)
                t["mig_arr"] = t["mig_s"] * SMS + t["mig_i"] / max(bsz, t["mig_i"] + 1) * SMS
            else: t["grp"] = None

    def arrival(self, s, i):
        b = self.bs.get(s, 400); return s * SMS + i / max(b, i + 1) * SMS

    def state_at(self, g, t):
        """pool state (B, Qv, F, j) at time t (ms) in group g: vectorized over arrays g, t"""
        g = np.asarray(g); t = np.asarray(t, np.float64)
        k = g.astype(np.int64) * 10**13 + np.round(t * 100).astype(np.int64)
        j = np.searchsorted(self.key, k, side="left")
        end = self.gend[g]; last = end - 1
        inside = j < end
        jj = np.where(inside, j, last)
        B = np.where(inside, self.B[jj], self.Bp[jj]); Q = np.where(inside, self.Qv[jj], self.Qp[jj])
        F = self.F[jj]
        return B, Q, F, j

    def sim(self, g, t_trig, p_ref, size=0.5, lat=35.0, guard=1.05, hold_ms=None, tp=None, sl=None, max_ms=600_000.0):
        """vectorized entry + exit. hold_ms: timer exit (decision = landing + hold). tp/sl: price multiple of the pool price
        at our fill (decision at the first trade crossing it, capped at max_ms). Returns dict of arrays."""
        g = np.asarray(g, np.int64); t_trig = np.asarray(t_trig, np.float64); p_ref = np.asarray(p_ref, np.float64)
        t_land = t_trig + lat
        B, Q, F, j = self.state_at(g, t_land)
        p_land = Q / B
        fail = p_land > guard * p_ref if guard else np.zeros(len(g), bool)
        X = size * 1e9
        e = X * 1e4 / (1e4 + F)
        out = B * e / (Q + e)
        if tp is None and sl is None:
            t_dec = t_land + hold_ms
        else:
            t_dec = np.empty(len(g))
            for n_ in range(len(g)):
                a = j[n_]; b = self.gend[g[n_]]
                if a >= b: t_dec[n_] = t_land[n_] + max_ms; continue
                tmax = t_land[n_] + max_ms
                hi = a + np.searchsorted(self.R["arr"][a:b], tmax, side="right")
                pp = self.R["p_post"][a:hi] / p_land[n_]
                hit = np.zeros(hi - a, bool)
                if tp: hit |= pp >= tp
                if sl: hit |= pp <= sl
                w = np.nonzero(hit)[0]
                t_dec[n_] = self.R["arr"][a + w[0]] if len(w) else tmax
        t_out = t_dec + lat
        B2, Q2, F2, j2 = self.state_at(g, t_out)
        q = Q2 * out / (B2 + out)
        proceeds = q * (1 - F2 / 1e4)
        pnl = (proceeds - X) / 1e9 - FIX
        pnl = np.where(fail, -FAIL, pnl)
        cens = t_out > self.end_arr
        return dict(g=g, t_land=t_land, t_out=t_out, pnl=pnl, fail=fail, cens=cens, p_land=p_land, ret=proceeds / X - 1, ahead=j - self.gstart[g])

def one_at_a_time(res, order=None):
    """greedy: take a trade if it lands after the previous taken trade's exit"""
    t_land = res["t_land"]; t_out = res["t_out"]; fail = res["fail"]
    o = np.argsort(t_land, kind="stable"); take = np.zeros(len(t_land), bool); busy = -1.0
    for k in o.tolist():
        if t_land[k] >= busy:
            take[k] = True
            busy = t_land[k] + 1.0 if fail[k] else t_out[k]
    return take

def stats(res, mask=None, hours=None):
    pnl = res["pnl"] if mask is None else res["pnl"][mask]
    fail = res["fail"] if mask is None else res["fail"][mask]
    n = len(pnl)
    if n == 0: return dict(n=0, pnl=0.0)
    ok = pnl[~fail]
    srt = np.sort(pnl)[::-1]
    top = max(1, n // 100)
    d = dict(n=n, fails=int(fail.sum()), pnl=round(float(pnl.sum()), 3), mean=round(float(pnl.mean()), 5),
             win=round(float((ok > 0).mean()), 3) if len(ok) else None, ex_top1pct=round(float(srt[top:].sum()), 3),
             med=round(float(np.median(pnl)), 5))
    if hours: d["per_day"] = round(d["pnl"] / hours * 24, 2)
    return d
