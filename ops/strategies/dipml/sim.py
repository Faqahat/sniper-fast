#!/usr/bin/env python3
"""VM1 independent check: my own trade simulator (no code from the copy).

A trade on dump k (global index into core.Data.T):
  entry position: block clock (dump + delay -> slot/index, spilling into the next produced block), fixed +N txs
                  (spill-aware), or the copy's CLAIM rule (+80 txs, never leaving the dump's slot, i.e. index i+81)
  entry state   : the token's reserves after its last trade strictly before our position
  guard         : revert if entry price > 1.05 x post-dump price
  buy           : x = S / (1 + fee) SOL into the curve, q = T - k/(V + x) tokens (k = V*T of the token)
  exit position : live-measured sell landing (slots after OUR buy slot + block position) or CLAIM (end of dump slot + 6)
  exit          : V' = V_exit + x (our buy kept in the curve: others' SOL flows unchanged), SOL out = V' - k/(k/V' + q),
                  minus the pump fee
  P&L before tx costs = net - S.  Follower cut and tx costs are applied by the caller (expected values).
All amounts in SOL. Expected values over a landing/exit sample set are returned per dump.
"""
import numpy as np
import core

def _next_block(D, slot):
    slot = np.asarray(slot, np.int64).copy()
    for _ in range(8):
        miss = D.bsize(slot) <= 0
        if not miss.any(): break
        slot[miss] += 1
    return slot

def entry_positions(D, kd, spec):
    """spec: ('clock', delta_slots) | ('fixed', N) | ('claim',)"""
    T = D.T; s = T["slot"][kd].astype(np.int64); i = T["idx"][kd].astype(np.int64)
    if spec[0] == "clock":
        t = D.clock(s, i) + spec[1]
        se, ie = D.position(t)
        same = (se == s) & (ie <= i); ie = np.where(same, i + 1, ie)
        return se, ie
    if spec[0] == "fixed":
        se = s.copy(); ie = i + spec[1]
        for _ in range(6):
            n = D.bsize(se).astype(np.int64); over = ie >= np.maximum(n, 1)
            if not over.any(): break
            ie = np.where(over, ie - np.maximum(n, 1), ie); se = np.where(over, _next_block(D, se + 1), se)
        return se, ie
    if spec[0] == "claim":
        return s, i + 81
    raise ValueError(spec)

def exit_positions(D, kd, se, spec):
    """spec: ('live', dslot, frac) sell lands dslot slots after our buy's slot at block fraction frac | ('claim',)"""
    if spec[0] == "claim":
        s = D.T["slot"][kd].astype(np.int64)
        return s + 7, np.zeros(len(kd), np.int64)
    sx = _next_block(D, se + spec[1])
    ix = np.floor(spec[2] * np.maximum(D.bsize(sx), 1)).astype(np.int64)
    return sx, ix

def trade(D, kd, entry_spec, exit_spec, S=0.3, guard=1.05):
    """one landing/exit sample for every dump: returns (filled bool, pnl_pre SOL (0 if reverted), entry slot, exit slot)"""
    T = D.T; m = T["mint"][kd]
    Vd = T["vsol"][kd].astype(np.float64); Td = T["vtok"][kd].astype(np.float64)
    f = (T["fee_bps"][kd].astype(np.float64) + T["cfee_bps"][kd].astype(np.float64)) / 1e4
    se, ie = entry_positions(D, kd, entry_spec)
    ke = D.state_before(m, se, ie)
    ke = np.where(ke < kd, kd, ke)                       # the dump itself is always before our position
    Ve = T["vsol"][ke].astype(np.float64); Te = T["vtok"][ke].astype(np.float64)
    K = Ve * Te
    x = S * 1e9 / (1 + f)
    q = Te - K / (Ve + x)
    qd = Td - (Vd * Td) / (Vd + x)                      # tokens at the post-dump state: the live guard's min_out = qd / guard
    filled = q >= qd / guard
    sx, ix = exit_positions(D, kd, se, exit_spec)
    kx = D.state_before(m, sx, ix); kx = np.where(kx < ke, ke, kx)
    Vx = T["vsol"][kx].astype(np.float64)
    V2 = Vx + x
    out = V2 - K / (K / V2 + q)
    net = out * (1 - f)
    pnl = np.where(filled, net / 1e9 - S, 0.0)
    return filled, pnl, se, sx

def expected(D, kd, entry_specs, exit_specs, S=0.3, guard=1.05):
    """mixture over paired samples: entry_specs[j] with exit_specs[j % len]; returns dict of per-dump arrays:
    p_fill, e_pos (mean positive part of pnl_pre), e_neg (mean negative part), p_spill"""
    n = len(kd); pf = np.zeros(n); ep = np.zeros(n); en = np.zeros(n); sp = np.zeros(n)
    sd = D.T["slot"][kd].astype(np.int64)
    J = len(entry_specs)
    for j, es in enumerate(entry_specs):
        xs = exit_specs[(j * 7919) % len(exit_specs)]
        fl, p, se, sx = trade(D, kd, es, xs, S, guard)
        pf += fl; ep += np.maximum(p, 0); en += np.minimum(p, 0); sp += se > sd
    return {"p_fill": pf / J, "e_pos": ep / J, "e_neg": en / J, "p_spill": sp / J}

def value(E, C, R, cut):
    """expected P&L per pick (SOL): follower cut on the positive part, tx cost C per filled trip, R per revert"""
    return (1 - cut) * E["e_pos"] + E["e_neg"] - C * E["p_fill"] - R * (1 - E["p_fill"])

def claim_value(filled, pnl, C, Rv, cut=0.2):
    """the copy's accounting: net = pnl - C; cut applied to positive NET; revert = -Rv"""
    net = pnl - C
    v = np.where(net > 0, net * (1 - cut), net)
    return np.where(filled, v, -Rv)

def take(slots, mints, max_open=1, busy=6):
    """position limit: picks in chain order; busy from the dump slot for `busy` slots; no second position on a held token"""
    o = np.argsort(slots, kind="stable"); took = np.zeros(len(slots), bool); open_ = []
    for q in o:
        s = slots[q]; open_ = [(e, mm) for e, mm in open_ if e >= s]
        if len(open_) >= max_open or any(mm == mints[q] for _, mm in open_): continue
        took[q] = True; open_.append((s + busy, mints[q]))
    return took
