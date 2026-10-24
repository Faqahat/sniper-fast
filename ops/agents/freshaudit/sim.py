#!/usr/bin/env python3
# pump curve replay helpers (exact constant product on virtual reserves, as in the TradeEvents)
import json, gzip
OURS = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"
BUY_TX = 506500; SELL_TX = 605000; SELL_TIP = 1_000_000
def load_tapes(p):
    return json.load(gzip.open(p, "rt"))
def trades(rows, drop_user=None):
    """flatten ok trade events -> [(s, i, k, is_buy, sol, tok, user, vsol, vtok, fbps, cbps)] in chain order"""
    out = []
    for r in rows:
        if r["err"]: continue
        for k, e in enumerate(r["ev"]):
            b, sol, tok, user, vs, vt, fb, cb = e
            if drop_user and user == drop_user: continue
            out.append((r["s"], r["i"], k, b, sol, tok, user, vs, vt, fb, cb))
    return out
def state_before(tr, pos):
    """post-state of the last trade strictly before pos=(s,i)"""
    st = None
    for t in tr:
        if (t[0], t[1]) >= pos: break
        st = (t[7], t[8])
    return st
def simulate(tr, entry_pos, ref_state, B, guard=1.05, exit_mode=("time", 5, 100), fr=0.0125, tp=1.05, sl=0.90, tip=3_000_000, follow_ok=True):
    """our buy of B SOL (incl. pump fee) lands at entry_pos; guard vs ref_state (post-dump state).
    exit_mode: ("time", dslots, idx) = sell at (land_s + dslots, idx); ("tpsl", dslots, idx, lag_idx) = TP/SL checked after each trade,
    sell lands lag_idx positions later in the same slot (or next slot start), else time exit.
    returns dict(fill, pnl_net, pnl_curve, entry_ratio, exit_pos) ; tr = trades WITHOUT our own wallet."""
    pre = state_before(tr, entry_pos)
    if pre is None: return None
    V, T = pre
    X = int(B * 1e9 / (1 + fr))
    q = T * X // (V + X)
    V0, T0 = ref_state
    q_exp = T0 * X // (V0 + X)
    ratio = (V / T) / (V0 / T0)
    if guard is not None and q * guard < q_exp:
        return dict(fill=False, pnl_net=-BUY_TX / 1e9, entry_ratio=ratio)
    V += X; T -= q
    land_s = entry_pos[0]
    mode = exit_mode[0]
    sell_pos = (land_s + exit_mode[1], exit_mode[2])
    trig = None
    for t in tr:
        pos = (t[0], t[1])
        if pos < entry_pos: continue
        if trig is not None and pos >= trig: break
        if pos >= sell_pos: break
        b, sol, tok = t[3], t[4], t[5]
        if b:
            d = T * sol // (V + sol); V += sol; T -= d
        else:
            so = V * tok // (T + tok); V -= so; T += tok
        if mode == "tpsl" and trig is None:
            val = (V * q // (T + q)) / X
            if val >= tp or val <= sl:
                lag = exit_mode[3]
                trig = (t[0], t[1] + lag)
    so = V * q // (T + q)
    gross = so - X
    net = so * (1 - fr) - B * 1e9 - BUY_TX - tip - SELL_TX - SELL_TIP
    return dict(fill=True, pnl_net=net / 1e9, pnl_curve=gross / 1e9, entry_ratio=ratio, trig=trig)

def simulate_stress(tr, entry_pos, ref_state, B, guard=1.05, hold=5, idx=100, fr=0.0125, tip=3_000_000, tol=0.05, rng=None):
    """like simulate(time exit) but follower BUYS fail (are dropped) when the curve price after our insertion exceeds
    the price they would have paid without us by more than tol (they carried a max-price guard of tol vs. what they saw)."""
    pre = state_before(tr, entry_pos)
    if pre is None: return None
    V, T = pre
    X = int(B * 1e9 / (1 + fr)); q = T * X // (V + X)
    V0, T0 = ref_state; q_exp = T0 * X // (V0 + X)
    if guard is not None and q * guard < q_exp: return dict(fill=False, pnl_net=-BUY_TX / 1e9, dropped=0)
    V += X; T -= q
    sell_pos = (entry_pos[0] + hold, idx); dropped = 0
    for t in tr:
        pos = (t[0], t[1])
        if pos < entry_pos: continue
        if pos >= sell_pos: break
        b, sol, tok, vs_real, vt_real = t[3], t[4], t[5], t[7], t[8]
        if b:
            # price the follower actually paid (real chain, without us) vs price with us
            real_pre_v = vs_real - sol; real_pre_t = vt_real + (vt_real and 0)
            p_real = (vs_real - sol) / max(1, (vt_real + (T0 * 0)))   # placeholder, replaced below
            # real pre-trade state: (vs_real - sol, vt_real + tokens_out); tokens_out = tok
            p_real = (vs_real - sol) / (vt_real + tok)
            p_ours = V / T
            if p_ours > p_real * (1 + tol):
                dropped += 1; continue
            d = T * sol // (V + sol); V += sol; T -= d
        else:
            so = V * tok // (T + tok); V -= so; T += tok
    so = V * q // (T + q)
    net = so * (1 - fr) - B * 1e9 - BUY_TX - tip - SELL_TX - SELL_TIP
    return dict(fill=True, pnl_net=net / 1e9, dropped=dropped)
