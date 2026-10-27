#!/usr/bin/env python3
# EXIT STUDY evaluation core: loads the e02 paths, values any exit policy on every trajectory (4 sell-landing rows), and runs the
# engine replay (both servers, near leaders, one open position per server, busy until the sell lands + 0.3 s, 0.2 s after a
# failed buy, 5 slots between picks on a token, FIX 0.0045 per round trip, FAIL 0.000505 per failed buy) with our MEASURED landing
# (Monte Carlo over the per-client landing deciles, common random numbers across policies) or a fixed 35 / 50 / 75 ms landing.
import os, sys, json, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import exit_lib as E

SPLIT = E.pk("10-25 01:00")         # train: 10-24 09:45 -> 10-25 01:00 PKT (15.25 h); test: 01:00 -> 09:45 (8.75 h)
VAL0 = E.pk("10-24 21:00")          # validation slice inside train (for choosing thresholds): 21:00 -> 01:00
W0, W1 = E.pk("10-24 09:45"), E.pk("10-25 09:45")
ROWS = ["meas", "35", "50", "75"]   # landing / sell-latency rows
TL_BUSY = 112.0; EV_BUSY = 55.0     # mean measured sell landing (ms after the decision) for the engine's busy time


class Data:
    def __init__(self, paths=None):
        T0 = time.time()
        self.D = dict(np.load(f"{E.DATA}/dumps.npz"))
        z = np.load(paths or f"{E.DATA}/paths/paths2.npz")
        self.ent = z["ent"]; self.trj = z["trj"]; self.ft = z["ft"]; self.tv = z["tv"].astype(np.float64)
        self.ev_a = z["ev_a"]; self.ev_s = z["ev_s"]; self.ev_b = z["ev_b"]; self.ev_sol = z["ev_sol"]; self.ev_c = z["ev_c"]
        self.ev_v = z["ev_v"].astype(np.float64); self.ev_sv = z["ev_sv"].astype(np.float64); self.ev_off = z["ev_off"]
        self.K = int(z["K"]); self.TF = [str(x) for x in z["tf"]]; self.TFI = {k: i for i, k in enumerate(self.TF)}
        nd = len(self.D["t"])
        did = self.ent[:, 0].astype(np.int64); li = self.ent[:, 1].astype(np.int64)
        self.NLI = int(li.max()) + 1 if len(li) else 1
        self.eidx = np.full((nd, max(self.NLI, 13)), -1, np.int64); self.tidx = np.full((nd, max(self.NLI, 13)), -1, np.int64)
        self.eidx[did, li] = np.arange(len(did))
        tdid = self.trj[:, 0].astype(np.int64); tli = self.trj[:, 1].astype(np.int64)
        self.tidx[tdid, tli] = np.arange(len(tdid))
        self.t_did = tdid; self.t_li = tli
        self.s_in = self.trj[:, 3].astype(np.int64); self.a_in = self.trj[:, 4]
        self.n_ev = np.diff(self.ev_off)
        self.ev_traj = np.repeat(np.arange(len(tdid)), self.n_ev)
        self.dump_t = self.D["t"]
        # dump-level crowd (real tape, for segmenting only): distinct target fast bots buying in the dump slot .. +3
        self.tg_n3 = np.zeros(nd); self.tg_sol3 = np.zeros(nd); self.hq3 = np.zeros(nd); self.bsol3 = np.zeros(nd)
        self.tg_n3[did] = self.ent[:, 6]; self.tg_sol3[did] = self.ent[:, 7]; self.hq3[did] = self.ent[:, 9]; self.bsol3[did] = self.ent[:, 11]
        self.size = E.SIZE
        print(f"data: {nd} dumps, {len(did)} entries, {len(tdid)} fills, {len(self.ev_a)} events ({time.time() - T0:.0f} s)", flush=True)

    # ---------- policy valuation: returns (val[N, 4], t_dec[N], kind[N]) over all trajectories
    def tick_policy(self, ksell):
        """ksell[N]: tick (1..K) where the sell is decided"""
        k = np.clip(np.asarray(ksell, np.int64), 1, self.K)
        val = self.tv[np.arange(len(k)), :, k]                    # [N, 4]
        tdec = (self.s_in + k) * E.SMS
        return val, tdec, np.zeros(len(k), np.int8)

    def first_event(self, cond, tcap):
        """first event index per trajectory where cond holds and the event is before the trajectory's cap decision time; -1 if none"""
        ok = cond & (self.ev_a < tcap[self.ev_traj])
        big = np.iinfo(np.int64).max
        idx = np.where(ok, np.arange(len(ok)), big)
        out = np.full(len(self.n_ev), big, np.int64)
        nz = self.n_ev > 0
        if nz.any():
            red = np.minimum.reduceat(idx, self.ev_off[:-1][nz])
            out[nz] = red
        out[out == big] = -1
        return out

    def combine(self, tick_val, tick_tdec, e_first):
        """earliest of an event trigger and the tick decision"""
        val = tick_val.copy(); tdec = tick_tdec.copy(); kind = np.zeros(len(tdec), np.int8)
        has = e_first >= 0
        if has.any():
            ef = e_first[has]; te = self.ev_a[ef]
            use = te < tdec[has]
            hi = np.flatnonzero(has)[use]
            val[hi] = self.ev_sv[ef[use]]; tdec[hi] = te[use]; kind[hi] = 1
        return val, tdec, kind

    def tpsl(self, cap, tp=None, sl=None, trail=None, trail_min=None):
        """time limit at tick `cap`, take-profit / stop-loss / trailing stop on the position value after each applied trade (event sell)"""
        kc = np.full(len(self.s_in), cap)
        val, tdec, kind = self.tick_policy(kc)
        cond = np.zeros(len(self.ev_a), bool)
        v = self.ev_v / self.size
        if tp is not None: cond |= v >= 1 + tp
        if sl is not None: cond |= v <= 1 - sl
        if trail is not None:
            seg = self.ev_traj.astype(np.float64)
            rm = np.maximum.accumulate(v + seg * 1000.0) - seg * 1000.0
            v0 = self.trj[:, 5] / self.size
            rm = np.maximum(rm, v0[self.ev_traj])
            c2 = v <= rm - trail
            if trail_min is not None: c2 &= rm >= 1 + trail_min
            cond |= c2
        ef = self.first_event(cond, tdec)
        return self.combine(val, tdec, ef)

    # ---------- per-trajectory P&L for a sell row r
    def pnl(self, val, r=0):
        return val[:, r] - self.size - E.FIX

    # ---------- engine replay
    def picks(self, which):
        D = self.D
        if which == "M2": return D["pick_m2"]
        if which == "IMIT1": return D["pick_im"]
        raise ValueError(which)

    def engine(self, sel_dumps, pnl_traj, tdec, kind, lmode="meas", R=24, seed=11, servers=("f", "a"), nobam=False, period=None,
               return_rows=False):
        """sel_dumps: bool over dumps. pnl_traj / tdec / kind: per trajectory. lmode: "meas" (MC over landing deciles 0..9) or "35"/"50"/"75".
        Returns dict(pnl (mean over replicates), fills, att, per-replicate totals, rows (dump, replicate, pnl) if asked)."""
        D = self.D
        if period is not None:
            sel_dumps = sel_dumps & (D["t"] >= period[0]) & (D["t"] < period[1])
        rng = np.random.default_rng(seed)
        nd = len(D["t"])
        if lmode == "meas": LI = rng.integers(0, 10, size=(R, nd))
        elif lmode == "measc": LI = rng.integers(13, 23, size=(R, nd))
        else:
            R = 1; LI = np.full((1, nd), {"35": 10, "50": 11, "75": 12}[lmode])
        tot = np.zeros(R); fills = np.zeros(R); att = np.zeros(R); rows = []
        busy_add = np.where(kind == 1, EV_BUSY, TL_BUSY) + 300.0
        for sv in servers:
            near = D["near_f"] if sv == "f" else (D["near_nb"] if nobam else D["near_a"])
            cand = np.flatnonzero(sel_dumps & near)
            cand = cand[np.argsort(D["arr"][cand], kind="stable")]
            tokkey = D["tag"][cand].astype(np.int64) * 10_000_000 + D["tok"][cand].astype(np.int64)
            arr = D["arr"][cand]; slot = D["s"][cand]
            for rep in range(R):
                busy = -1e18; last = {}
                li_r = LI[rep, cand]
                for x in range(len(cand)):
                    a = arr[x]
                    if a < busy: continue
                    d = cand[x]; li = li_r[x]
                    ei = self.eidx[d, li]
                    if ei < 0: continue
                    st = self.ent[ei, 3]
                    if st == 2: continue
                    tk = tokkey[x]
                    if tk in last and slot[x] < last[tk] + 5: continue
                    last[tk] = slot[x]; att[rep] += 1
                    if st == 1:
                        tot[rep] -= E.FAIL; busy = a + 200.0
                        if return_rows: rows.append((d, rep, -E.FAIL, 0))
                        continue
                    ti = self.tidx[d, li]
                    p = pnl_traj[ti]; tot[rep] += p; fills[rep] += 1
                    busy = tdec[ti] + busy_add[ti]
                    if return_rows: rows.append((d, rep, p, 1))
        out = dict(pnl=float(tot.mean()), fills=float(fills.mean()), att=float(att.mean()), reps=tot, R=R)
        if return_rows: out["rows"] = rows
        return out


def hours(period):
    return (period[1] - period[0]) / 3600.0


def block_boot(rows_a, rows_b, period, R, block_s=1800, B=2000, seed=5):
    """paired block bootstrap (30-min blocks) of the SOL/day difference between two engine runs (rows from engine(return_rows=True))"""
    nb = int(np.ceil((period[1] - period[0]) / block_s))
    def per_block(rows, D_t):
        v = np.zeros(nb)
        for d, rep, p, f in rows:
            b = int((D_t[d] - period[0]) // block_s); v[min(b, nb - 1)] += p / R
        return v
    return nb, per_block


def fmt_day(x, period):
    return x * 24.0 / hours(period)
