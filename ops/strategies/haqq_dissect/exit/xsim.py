"""EXIT analyst: exact-curve exit simulator for one position (read-only).
A position = our (or haqq's) buy inserted at its ACTUAL tape position; later outside trades replayed with the exact instruction
semantics (buys keep their SOL in, sells keep their tokens in; dv8sim.pnl_exact, validated to +0.02 mSOL/fill on our 595 live
fills). fol < 1 scales every outside buy's SOL after the entry (fewer followers) - also in the triggers.
Exit landing: a reactive trigger at outside row j (chain clock t_j) lands at t_j + d, d over the MEASURED quantiles of our
trigger -> sell landing delay (x3: pre-send TP/SL + regular TP/SL, n = 285); a timer exit decided at the start of slot
entry+N lands at slot start + d, d over the MEASURED quantiles of our timer sells (x3, per kind). The sell sits after every
outside row landed at or before its landing time. Value = expectation over the delay quantiles."""
import numpy as np
SMS = 212.0
QS = (5, 15, 25, 35, 45, 55, 65, 75, 85, 95)


class Pos:
    def __init__(self, p, fol=1.0):
        self.p = p; self.fol = fol
        dcc, bu, so, tk = p["dcc"], p["bu"], p["so"], p["tk"]
        self.dcc = dcc; self.bu = bu; self.n = len(dcc)
        self.sol = np.where(bu, so * fol, so)                     # outside buy SOL as seen (scaled)
        V0, T0 = p["V0"], p["T0"]; K = V0 * T0; self.K = K; fee = p["fee"]; self.fee = fee
        V = V0 + p["sin"]; T = K / V; self.tok = T0 - T; self.cost = p["cost"]
        Vs = np.empty(self.n); Ts = np.empty(self.n)
        for a in range(self.n):
            if bu[a]: V += self.sol[a]; T = K / V
            else: T += tk[a]; V = K / T
            Vs[a] = V; Ts[a] = T
        self.Vs = Vs; self.Ts = Ts
        self.v_pre = (p["V0"] + p["sin"] - K / (K / (p["V0"] + p["sin"]) + self.tok)) * (1 - fee) / self.cost
        self.v = (Vs - K / (Ts + self.tok)) * (1 - fee) / self.cost if self.n else np.zeros(0)
        self.vmax = np.maximum.accumulate(self.v) if self.n else self.v
        self.b_cc_in_slot = p["off_in_slot"]

    # ---- timing
    def q_at(self, t):
        return np.searchsorted(self.dcc, t, side="right") - 1

    def val_q(self, q):
        q = np.asarray(q)
        return np.where(q < 0, self.v_pre, self.v[np.clip(q, 0, max(self.n - 1, 0))] if self.n else self.v_pre)

    def slot_start(self, N):
        return N * SMS - self.b_cc_in_slot

    def land_val(self, t_trig, D):
        """exit value for a trigger at chain-clock time t_trig (ms after our buy), delay quantiles D"""
        return float(np.mean(self.val_q(self.q_at(t_trig + np.asarray(D)))))

    def timer_val(self, N, DT):
        return self.land_val(self.slot_start(N), DT)

    # ---- first trigger rows (index into outside rows) or None
    def first(self, mask, after_t=-1e9):
        m = mask & (self.dcc > after_t)
        if not m.any(): return None
        return int(np.argmax(m))

    def partial_exact(self, plan):
        """plan = [(landing time ms, fraction of the ORIGINAL tokens)] in time order -> total SOL out / cost (exact, sequential:
        each of our sells moves the curve for the next one). Landing time -> after every outside row at or before it."""
        p = self.p; K = self.K; fee = self.fee
        V = p["V0"] + p["sin"]; T = K / V; left = self.tok; got = 0.0; a = 0
        for t, fr in plan:
            q = int(self.q_at(t))
            while a <= q and a < self.n:
                if self.bu[a]: V += self.sol[a]; T = K / V
                else: T += p["tk"][a]; V = K / T
                a += 1
            tk = min(left, fr * self.tok)
            got += (V - K / (T + tk)) * (1 - fee); T += tk; V = K / T; left -= tk
        return got / self.cost
