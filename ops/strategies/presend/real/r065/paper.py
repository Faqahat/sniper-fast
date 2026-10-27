#!/usr/bin/env python3
"""REPLAY_065: the engine's PAPER pre-send (the shadow, src/presend.rs Path) re-computed at other sizes from its own fills.
A port of Path::new / feed / exit (floats, the shadow's own follower model: a follower buy is dropped when our buy breaks the
slack drawn for its signature from the 711-value table, sha256("dip" + signature)), on the chain tape (every trade of the
token in chain order, OUR live trades included, as the shadow saw them). Checked first against the engine's own logged
paper P&L at 0.55 SOL (MEASURED); the 0.34 / 0.65 numbers are the same model at that size (INFERRED)."""
import json, math, hashlib
import numpy as np

SMS = 212.0
SELL_LAT = 75.0
GRADV = 110e9
HMAX = 40
SLACK = [float(np.float32(min(r[1], 1e6))) for r in sorted(json.load(open("/home/moiz/sniper/ops/overnight/verify2/work/a8_slack.json"))["rows"], key=lambda r: r[1])]


def slack_of_sig(sig):
    d = hashlib.sha256(b"dip" + sig.encode()).digest()
    x = int.from_bytes(d[:4], "big") / 4294967296.0
    k = min(int(x * len(SLACK)), len(SLACK) - 1)
    return SLACK[k]


def arrival(s, i): return s * SMS + i / max(400.0, i + 1.0) * SMS


def fee_rate(fb, cb): return float(np.float32(((fb if fb != 0 else 95) + (cb if cb != 0 else 30)) / 1e4))


def py_floordiv(a, b): return math.floor(a / b)


def path(trades, m_idx, a_land, size_sol, slip=True, tp=0.10, sl=0.20, c=2, skip_sigs=()):
    """trades: the token's chain-ordered trades (dicts with s, i, buy, sol, tok, vsol, vtok, fbps, cbps, sig); m_idx: the index of m.
    Returns the exit value (gross SOL after pump's fee - size) as the shadow computes it, or None (untradeable)."""
    m = trades[m_idx]
    fr0 = fee_rate(m["fbps"], m["cbps"]); vb = float(m["vsol"]); tb = float(m["vtok"])
    if vb >= 100e9: return None
    x = size_sol * 1e9 / (1.0 + fr0); q = tb * x / (vb + x); v = vb + x; t = tb - q
    s_land = py_floordiv(a_land, SMS); s_in = max(m["s"], s_land)
    frs = fr0
    cur = v * q / (t + q) * (1.0 - frs) / 1e9 - size_sol
    poff = []; ftp = fsl = None; stop = False; last_s = None
    for r in trades[m_idx + 1:]:
        if r["sig"] in skip_sigs: continue
        sj = r["s"]
        a = arrival(r["s"], r["i"])
        pos = a - sj * SMS
        kj = 2 * sj + (1 if pos >= SELL_LAT else 0)
        while len(poff) <= HMAX + 1 and 2 * (s_in + len(poff)) + 1 <= kj: poff.append(cur)
        if sj > s_in + HMAX + 1 or len(poff) > HMAX + 1: stop = True; break
        applied = True
        if r["buy"]:
            sol = float(r["sol"]); dt = t * sol / (v + sol)
            if slip and dt < r["tok"] / (1.0 + slack_of_sig(r["sig"])): applied = False
            else: v += sol; t -= dt
        else:
            tk = float(r["tok"]); so = v * tk / (t + tk); v -= so; t += tk
        if applied: frs = fee_rate(r["fbps"], r["cbps"])
        cur = v * q / (t + q) * (1.0 - frs) / 1e9 - size_sol
        last_s = sj
        if v >= GRADV: stop = True; break
        if applied:
            val = (cur + size_sol) / size_sol
            if tp > 0 and ftp is None and val >= 1.0 + tp: ftp = sj
            if sl > 0 and fsl is None and val <= 1.0 - sl: fsl = sj
        # early out: once past the time limit and every needed boundary recorded
        if sj > s_in + c + 2 and len(poff) > c + 1: break
    co = s_in + c
    a_ = ftp if (ftp is not None and ftp + 1 < co) else None
    b_ = fsl if (fsl is not None and fsl + 1 < co) else None
    trig = min([z for z in (a_, b_) if z is not None], default=None)
    so = co if trig is None else trig + 1
    dd = so - s_in
    val = poff[dd] if len(poff) > dd else cur
    why = "time" if trig is None else ("tp" if trig == a_ and (b_ is None or a_ < b_) else ("sl" if trig == b_ and (a_ is None or b_ < a_) else "tp_sl"))
    return dict(val=val, dd=dd, why=why, so=so, s_in=s_in, q=q, x=x)
