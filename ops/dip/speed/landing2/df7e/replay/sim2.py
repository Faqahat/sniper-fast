#!/usr/bin/env python3
"""DF7e replay: event-driven simulator with a position limit (read-only, my own code on the VM1 data model).

One Monte-Carlo pass = candidates in chain order; for each candidate:
  - free positions whose exit (or revert) landed before the trigger; skip if full or the token is already held
  - our buy lands at block-clock(trigger) + d, d drawn from a landing sample set (slot units), spill-aware
    (core.Data.position); never before the trigger
  - entry state = the token's reserves after its last trade strictly before our position (others' buys ahead included)
  - guard: revert if tokens < tokens-at-the-post-trigger-price / guard  (guard 1.05 = our +5%; 1.18 = his -18%)
  - buy: x = S/(1+fee) SOL into the curve; q = T - K/(V + x)
  - exit (filled):
      'timer'  : hold H slots drawn from his measured hold distribution (buy slot -> sell slot), sell at a random block position
      'trail'  : from buy slot + MINH, the first others' trade that leaves the price >= TRAIL below the peak since entry,
                 or Q slots without a trade, or MAXH slots -> decision; the sell lands decision + d2 (same landing set)
      'fixed'  : sell lands buy slot + H0 at a random block position
    sale on the reserves just before our sell, our buy kept in the curve: V2 = Vx + x, out = V2 - K/(K/V2 + q), minus fee
  - a token whose curve completes (graduation) before our sell: exit at its last curve price (flag 'grad'; PumpSwap exit not modelled)
Returns one row per taken candidate: [cand id, filled, pnl_pre SOL, hold slots, grad, entry slot, ahead buys]
"""
import numpy as np
import core

def _next_block(D, s):
    for _ in range(8):
        if D.bsize(np.array([s]))[0] > 0: return s
        s += 1
    return s

def clock1(D, s, i):
    n = int(D.bsize(np.array([s]))[0]) or 1
    return s + min(i / n, 0.999999)

def pos1(D, t):
    se, ie = D.position(np.array([t]))
    return int(se[0]), int(ie[0])

def before(D, m, s, i):
    """global index of token m's last trade strictly before (s, i), or -1"""
    return int(D.state_before(np.array([m]), np.array([s]), np.array([i]))[0])

class Sim:
    def __init__(self, D, S=0.5, guard=1.05, exit=("timer",), holds=None, land=None, max_open=1, seed=0):
        self.D = D; self.S = S; self.guard = guard; self.exit = exit; self.holds = holds; self.land = np.asarray(land)
        self.max_open = max_open; self.rng = np.random.default_rng(seed)
        T = D.T
        self.slot = T["slot"]; self.idx = T["idx"]; self.vsol = T["vsol"]; self.vtok = T["vtok"]; self.mint = T["mint"]; self.buy = T["buy"]
        self.fee = (T["fee_bps"].astype(np.float64) + T["cfee_bps"].astype(np.float64)) / 1e4

    def _exit_trail(self, m, se, ie, ke, x, MINH, TRAIL, Q, MAXH):
        D = self.D; a = ke + 1; b = D.mend[m]
        # trades after our entry position (ke = last trade before us; the trades between ke and our position: none by construction)
        sl = self.slot[a:b].astype(np.int64); ix = self.idx[a:b].astype(np.int64)
        after = (sl > se) | ((sl == se) & (ix >= ie))
        a2 = a + int(np.argmax(after)) if after.any() else b
        hi = a2 + int(np.searchsorted(self.slot[a2:b].astype(np.int64), se + MAXH, "right"))
        S_ = self.slot[a2:hi].astype(np.int64); V = self.vsol[a2:hi].astype(np.float64) + x
        V0 = float(self.vsol[ke]) + x
        t_dec = se + MAXH + 0.0
        if len(S_):
            pk = np.maximum.accumulate(np.concatenate([[V0], V]))[1:]
            dd = 1 - (V / pk) ** 2
            j = np.where((S_ >= se + MINH) & (dd >= TRAIL))[0]
            if len(j): t_dec = min(t_dec, clock1(D, int(S_[j[0]]), int(self.idx[a2 + j[0]])))
            # quiet: Q slots with no trade, counted from the last trade (or from our entry)
            prev = np.concatenate([[se], S_]); nxt = np.concatenate([S_, [se + MAXH + Q + 10]])
            qq = np.where(nxt - prev > Q)[0]
            if len(qq):
                tq = max(float(prev[qq[0]] + Q + 1), float(se + MINH)); t_dec = min(t_dec, tq)
        else:
            t_dec = min(t_dec, float(se + max(MINH, Q + 1)))
        t_dec = max(t_dec, float(se + MINH))
        d2 = float(self.land[self.rng.integers(len(self.land))])
        return pos1(D, t_dec + d2)

    def run(self, cand, cls=None):
        """cand: global trade indices of triggers, chain order not required"""
        D = self.D; S = self.S
        order = np.lexsort((self.idx[cand], self.slot[cand])); cand = np.asarray(cand)[order]
        open_ = []   # (end clock, mint)
        out = []
        for c, k in zip(order, cand):
            k = int(k); m = int(self.mint[k]); s = int(self.slot[k]); i = int(self.idx[k])
            tk = clock1(D, s, i)
            if open_: open_ = [(e, mm) for e, mm in open_ if e > tk]
            if len(open_) >= self.max_open or any(mm == m for _, mm in open_): continue
            d = float(self.land[self.rng.integers(len(self.land))])
            se, ie = pos1(D, tk + d)
            if se == s and ie <= i: ie = i + 1
            ke = before(D, m, se, ie)
            if ke < k: ke = k
            f = self.fee[k]; x = S * 1e9 / (1 + f)
            Ve = float(self.vsol[ke]); Te = float(self.vtok[ke]); K = Ve * Te
            q = Te - K / (Ve + x)
            Vd = float(self.vsol[k]); Td = float(self.vtok[k]); qd = Td - Vd * Td / (Vd + x)
            ahead = int(np.sum(self.buy[k + 1:ke + 1] == 1)) if ke > k else 0
            if q < qd / self.guard:
                out.append([int(c), 0, 0.0, 0, 0, se, ahead]); open_.append((clock1(D, se, ie), m)); continue
            ex = self.exit
            if ex[0] == "timer":
                H = int(self.holds[self.rng.integers(len(self.holds))])
                sx = _next_block(D, se + H); ix = int(self.rng.random() * max(int(D.bsize(np.array([sx]))[0]), 1))
            elif ex[0] == "fixed":
                sx = _next_block(D, se + ex[1]); ix = int(self.rng.random() * max(int(D.bsize(np.array([sx]))[0]), 1))
            else:
                sx, ix = self._exit_trail(m, se, ie, ke, x, *ex[1:])
            kx = before(D, m, sx, ix)
            if kx < ke: kx = ke
            last = int(D.mend[m]) - 1
            grad = int(kx == last and int(self.D.T["rsol"][last]) >= 84_000_000_000)   # curve completed before our sell: exit at its last curve price
            Vx = float(self.vsol[kx]); V2 = Vx + x
            outsol = V2 - K / (K / V2 + q)
            pnl = outsol * (1 - f) / 1e9 - S
            out.append([int(c), 1, pnl, int(sx - se), grad, se, ahead])
            open_.append((clock1(D, sx, ix), m))
        return np.array(out, dtype=np.float64).reshape(-1, 7)

def value(rows, C, R, cut, bias=0.0):
    """per-row P&L after follower cut on positive pre-cost P&L, tx cost C per fill, R per revert, optional bias per fire"""
    fl = rows[:, 1] == 1; p = rows[:, 2]
    v = np.where(fl, (1 - cut) * np.maximum(p, 0) + np.minimum(p, 0) - C, -R)
    return v - bias
