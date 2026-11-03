"""YOUNG simulator: pre-sent buy fill + exit on the chain tape (our own wallets removed, curve re-played by deltas).
Fill model (MEASURED on live, c0): our try lands right after the dump that brings the price under the limit, same slot
(77% of live fills have 0 trades between). Exit model: sell lands at slot fill+H (live: H=2 62%, 1 25%), executes after
`pos` share of the other trades of that slot (calibrated in y3_calib). Costs: fixed per round trip + failed tries."""
from ylib import OURS, FEE

LIVE_MIX = [(1, 0.66, 0.18), (2, 0.39, 0.72), (3, 0.11, 0.10)]  # MEASURED live sell landing (c3)

def replay_state(vs, vt, x):
    """apply other trade x (buy: its SOL; sell: its tokens) to (vs, vt)."""
    if x[3]:
        sol = x[4]; tok = vt * sol / (vs + sol); return vs + sol, vt - tok
    tok = x[5]; sol = vs * tok / (vt + tok); return vs - sol, vt + tok


def sim(r, tape, size=0.696, lim_mult=0.88, window=10, need_sells=1, dumper=None, min_drop=0.0,
        mix=None, tp=None, sl=None, cost_rt=0.0, try_cost=5120e-9, tries_per_slot=None, skip_first=0, limref="slotstart", scen=(0, 0), quiet_stop=True, whale_stop=True, end_slot=None):
    """returns None (no tape) or dict(filled, pnl, ...). dumper: None | 'whale' | 'notwhale'.
    hold: sell landing slot offset; 'pos' = fraction of other trades of the landing slot that go before our sell.
    tp/sl: fractional move of the sell value vs cost; checked on each other trade after fill in slots < landing slot;
    a hit moves the sell landing to (hit slot + 1)."""
    if not tape: return None
    mix = mix or LIVE_MIX
    trig = (r["slot"], r["idx"], r.get("j", 0))
    oth = [x for x in tape if x[8] not in OURS and (x[0], x[1], x[2]) > trig and x[0] <= r["slot"] + window + 40]
    vs, vt = r["vsol"], r["vtok"]
    p0 = vs / vt; lim = p0 * lim_mult
    net = size / (1 + FEE) * 1e9
    nsell = 0; fill = None; k = 0; others = 0; ref = (vs, vt); prev_slot = r["slot"]; last = r["slot"] + window
    states = []  # state after each other trade
    for k, x in enumerate(oth):
        if x[0] > last + 1: break
        if x[0] != prev_slot: prev_slot = x[0]; slot_ref = (vs, vt)
        vs, vt = replay_state(vs, vt, x)
        states.append((vs, vt))
    vs, vt = r["vsol"], r["vtok"]; ref_at = {}
    pv = (vs, vt); ps = r["slot"]
    for k, x in enumerate(oth[:len(states)]):
        if x[0] != ps: ref_at[x[0]] = pv; ps = x[0]
        pv = states[k]
    ref_at.setdefault(r["slot"], (r["vsol"], r["vtok"]))
    stop_k = len(states)
    for k, x in enumerate(oth[:len(states)]):
        if x[0] > last: stop_k = k; break
        if quiet_stop and x[0] >= r["slot"] + 6 and others < 2: stop_k = k; break
        if x[8] != r["wallet"]: others += 1
        if x[3]: continue
        whale = x[8] == r["wallet"]
        ok = not ((dumper == "whale" and not whale) or (dumper == "notwhale" and whale))
        if ok:
            nsell += 1
            if nsell >= need_sells:
                # our next try lands at (slot + scen[0], idx + scen[1]) (scen[0] = 1: idx = scen[1] from the slot start)
                ls = x[0] + scen[0]; li = (x[1] + scen[1]) if scen[0] == 0 else scen[1]
                if ls <= last:
                    kk = k
                    while kk + 1 < len(states) and (oth[kk + 1][0], oth[kk + 1][1]) < (ls, li): kk += 1
                    rv = ref_at.get(ls if scen[0] else x[0], ref_at[r["slot"]]) if limref == "slotstart" else (states[k - 1] if k else (r["vsol"], r["vtok"]))
                    lim = rv[0] / rv[1] * lim_mult
                    v1, t1 = states[kk]
                    if v1 / t1 <= lim and (1 - (v1 / t1) / p0) >= min_drop:
                        tok = t1 * net / (v1 + net)
                        if tok >= net / lim * 0.978:
                            fill = (kk, x, tok, ls); vs, vt = v1 + net, t1 - tok
                            break
        if whale and whale_stop: stop_k = k; break
    nslots = (fill[3] - r["slot"] + 1) if fill else min(window, (oth[stop_k][0] - r["slot"] + 1) if stop_k < len(oth) else window)
    tries = (tries_per_slot or 0) * nslots
    if not fill:
        return {"filled": False, "pnl": -tries * try_cost, "tries": tries}
    k, d, tok, fs = fill
    rest = oth[k + 1:]
    st0 = (vs, vt)
    # TP / SL scan (decided on a trade; sell lands from the next slot)
    hit = None
    if tp is not None or sl is not None:
        v2s, v2t = vs, vt
        for x in rest:
            if x[0] >= fs + max(h for h, _, _ in mix): break
            v2s, v2t = replay_state(v2s, v2t, x)
            val = v2s * tok / (v2t + tok) * (1 - FEE) / 1e9
            if (tp is not None and val >= size * (1 + tp)) or (sl is not None and val <= size * (1 - sl)):
                hit = max(x[0] + 1, fs + 1); break
    gross = 0.0; nsh = 0.0; ssh = 0.0
    for h, pos, w in mix:
        land = fs + h
        if hit is not None and hit < land: land, pos = hit, 0.39
        inslot = [x for x in rest if x[0] == land]
        npre = int(round(len(inslot) * pos))
        vs, vt = st0; a_n = 0; a_s = 0
        for x in rest:
            if x[0] > land or (x[0] == land and npre <= 0): break
            if x[0] == land: npre -= 1
            vs, vt = replay_state(vs, vt, x)
            if not x[3]: a_n += 1; a_s += x[4]
        g = vs * tok / (vt + tok)
        gross += w * (g * (1 - FEE) / 1e9 - size); nsh += w * a_n; ssh += w * a_s / 1e9
    pnl = gross - cost_rt - tries * try_cost
    return {"filled": True, "pnl": pnl, "gross": gross, "fill_slot": fs, "d_slot": fs - r["slot"], "dump_user": d[8], "dump_is_whale": d[8] == r["wallet"],
            "dump_sol": d[4] / 1e9, "drop": 1 - (d[6] / d[7]) / p0, "nsell_hold": nsh, "sell_sol_hold": ssh, "tries": tries, "tok": tok, "tp_hit": hit is not None}


# MEASURED (c6): first live try after a qualifying dump: same slot 82% (idx gap q10..q90 11/22/48/97/174), next slot 18%
SAME = [8, 13, 19, 26, 36, 48, 63, 85, 115, 175]
NEXT = [30, 55, 80, 110, 144, 190, 250, 320, 420, 573]
SCEN = [((0, g), 0.082) for g in SAME] + [((1, g), 0.018) for g in NEXT]

def esim(r, tape, **kw):
    """expected outcome over the measured landing scenarios"""
    out = {"p_fill": 0.0, "pnl": 0.0, "gross_f": 0.0, "dump_is_whale": 0.0, "nsell_hold": 0.0, "sell_sol_hold": 0.0, "drop": 0.0, "d_slot": 0.0}
    if not tape: return None
    for sc, w in SCEN:
        s = sim(r, tape, scen=sc, **kw)
        out["pnl"] += w * s["pnl"]
        if s["filled"]:
            out["p_fill"] += w; out["gross_f"] += w * s["gross"]
            for k in ("dump_is_whale", "nsell_hold", "sell_sol_hold", "drop", "d_slot"): out[k] += w * s[k]
    return out
