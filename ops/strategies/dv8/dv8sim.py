"""DV8 replay mechanics (read-only). Tape rows of ONE mint (our own wallets' rows removed), chain order.
Entry  = our buy inserted before row r (state = reserves after row r-1).
Exit   = sell all our tokens after row q (inclusive), q >= r-1.
Follower models: 'vshift' (s7: every later trade keeps its SOL effect, V_exit = V_tape[q] + our SOL),
                 'exact'  (later buys keep their SOL in, later sells keep their TOKENS in - the real instruction semantics; sequential).
Pump fee 1.25% each side (FEE)."""
import numpy as np
FEE = 0.0125


def entry_tokens(v0, t0, size):
    sn = size / (1 + FEE); K = v0 * t0
    return t0 - K / (v0 + sn)


def pnl_vshift(vs, vt, r, q, size, fol=1.0, cb=None):
    """s7 method; fol<1 removes (1-fol) of outside buy SOL between entry and exit (cb = cumulative outside buy SOL)"""
    v0 = vs[r - 1]; t0 = vt[r - 1]; K = v0 * t0
    sn = size / (1 + FEE); v1 = v0 + sn; tok = t0 - K / v1
    dv = vs[q] - v0
    if fol != 1.0 and cb is not None: dv -= (1 - fol) * (cb[q] - cb[r - 1])
    V = v1 + dv
    if V <= 0: return -size
    return (V - K / (K / V + tok)) * (1 - FEE) - size


def pnl_exact(vs, vt, sol, tok_, buy, r, q, size, fol=1.0, outside=None):
    """sequential: buys keep SOL, sells keep tokens; fol<1 scales outside BUY SOL (fewer followers)"""
    v0 = float(vs[r - 1]); t0 = float(vt[r - 1]); K = v0 * t0
    sn = size / (1 + FEE); V = v0 + sn; T = K / V; tok = t0 - T
    for k in range(r, q + 1):
        if buy[k]:
            s = float(sol[k]) * (fol if (outside is None or outside[k]) else 1.0)
            V += s; T = K / V
        else:
            T += float(tok_[k]); V = K / T
    return (V - K / (T + tok)) * (1 - FEE) - size
