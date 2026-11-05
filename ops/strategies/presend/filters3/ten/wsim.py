#!/usr/bin/env python3
"""TEN: pre-send WINDOW replay on the raw recording (p2 rows), for levers that ADD windows (re-arm on older tokens, re-arm with no
holder, longer T2 windows) and for exits. A model, so every number from it is an ESTIMATE; it is calibrated on the live windows of the
same hours (validate()).
Curve: constant product K = vsol * vtok, vtok = curve token balance + 73e12 (checked on our own fills: exact). Our own rows are
removed; others' trades are replayed as fixed curve SOL (buys) / fixed tokens (sells) on our state.
Fill: in the window's slots, right after a sell whose post price <= (1 - drop) x ref, ref = the highest price seen since the end of
the previous slot (an attempt signed on it, deadline +1). Entry right after that trade (live pre-send fills land median 4 ms after it).
Stops: T2 = the whale's first sell (it can still fill us, as live); quiet N:M = fewer than M trades by others (not whale, not us) in
the slots arm..arm+N-1 -> stop at arm+N; re-arm = a single sell >= 6% supply (fills, then stops) or no tracked holder >= 6% left.
Exit: sell after the last trade of slot fill+1 (live sells land at +1 or +2), or the exit rule given. Costs: 1.25% each way,
FIXED 3.5 mSOL per trip (median live), failed tries per armed window (live mean: T2 0.25, re-arm 0.34 mSOL)."""
import json
K = 30e9 * 1.073e15
OFF = 73e12
SUP = 1e15
FEE = 0.0125
FIXED = 0.0035
ME = "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"

def dedup(rows):
    """dedup (s, i); keep only rows whose curve change equals the signer's token change (a real swap on the curve: cpost - cpre ==
    -tok). A row whose cpre does not continue the chain is SKIPPED when one of the next 4 valid rows continues it (the p2 extract took
    another account as the curve, seen on dust trades); otherwise the gap becomes a PHANTOM row by wallet '?' carrying exactly that
    curve change (a swap the extract did not see as the signer's, e.g. routed), so the state always follows the chain."""
    seen, val = set(), []
    for r in rows:
        k = (r[0], r[1])
        if k in seen: continue
        seen.add(k)
        if r[3] == 0 or abs((r[6] - r[5]) + r[3]) > 1000: continue
        val.append(tuple(r))
    out, last = [], None
    for j, r in enumerate(val):
        if last is not None and r[5] != last[6]:
            if any(x[5] == last[6] for x in val[j + 1:j + 5]): continue
            out.append((r[0], (r[1] or 0) - 0.5, "?", -(r[5] - last[6]), 0, last[6], r[5]))
        out.append(r); last = r
    return out

class Curve:
    def __init__(self, vt): self.vt = vt
    @property
    def vs(self): return K / self.vt
    @property
    def p(self): return self.vs / self.vt
    def apply(self, r):
        """r = (s, i, u, tok, sol, cpre, cpost): replay as fixed SOL (buy) or fixed tokens (sell); returns (is_buy, sol_c, tok_c)"""
        vpre, vpost = r[5] + OFF, r[6] + OFF
        if vpost < vpre:                           # buy: curve gets SOL
            sol_c = K / vpost - K / vpre
            vs = self.vs + sol_c; self.vt = K / vs
            return True, sol_c, vpre - vpost
        dt = vpost - vpre
        self.vt += dt
        return False, K / vpre - K / vpost, dt

def balances(rows, upto):
    """token balances by wallet from the token's whole history (None if the history does not start at the create)"""
    if not rows or rows[0][5] != 0: return None
    b = {}
    for r in rows:
        if (r[0], r[1] or 0) > upto: break
        b[r[2]] = b.get(r[2], 0) + r[3]
    return b

def sim_window(rows, arm_slot, end_slot, size, drop=0.12, kind="t2", whale=None, qstop=(5, 2), holders=None,
               exit_rule=None, drop_share=0.0, seed=0, exclude=(ME,), refmode="slot"):
    """returns dict(filled, pnl, fill_slot, ...) ; pnl includes trip costs (not the failed-try fee)"""
    rows = [r for r in rows if r[2] not in exclude]
    pre = [r for r in rows if r[0] < arm_slot]
    if not pre: return None
    cv = Curve(pre[-1][6] + OFF)
    hold = dict(holders or {})                   # wallet -> balance (raw tokens)
    others = 0; ref = cv.p; cur_slot = None; fill = None; stop_why = None
    for r in rows:
        s = r[0]
        if s < arm_slot: continue
        if s > end_slot: stop_why = "expired"; break
        if qstop and s >= arm_slot + qstop[0] and others < qstop[1]: stop_why = "quiet"; break
        if s != cur_slot:
            cur_slot = s; ref = cv.p
        p_before = cv.p
        ref = max(ref, p_before) if refmode == "slot" else p_before
        is_buy, sol_c, tok_c = cv.apply(r)
        if r[2] != whale: others += 1
        if r[2] in hold: hold[r[2]] += r[3]
        if not is_buy and cv.p <= (1 - drop) * ref:
            fill = (s, r[1]); break
        if kind == "t2" and whale and r[2] == whale and not is_buy: stop_why = "whale_sold"; break
        if kind == "rearm":
            if not is_buy and tok_c >= 0.06 * SUP: stop_why = "whale_dump"; break
            if hold and max(hold.values()) < 0.06 * SUP: stop_why = "no_holder"; break
    if not fill: return {"filled": False, "pnl": 0.0, "why": stop_why or "end"}
    # entry right after the fill trade
    x_in = size * 1e9 / (1 + FEE)
    vs = cv.vs + x_in; cv.vt = K / vs
    vt_after_buy = cv.vt
    mytok = None
    # tokens bought: from the state before our buy
    mytok = (K / (vs - x_in)) - vt_after_buy
    post = [r for r in rows if (r[0], r[1] or 0) > fill]
    exit_slot = fill[0] + 2
    n_fol = 0
    import hashlib
    for r in post:
        if exit_rule is not None:
            ex = exit_rule(r, fill, n_fol)
            if ex: break
        elif r[0] >= exit_slot: break
        vpre, vpost = r[5] + OFF, r[6] + OFF
        if vpost < vpre:
            if drop_share and int(hashlib.sha256(f"{seed}:{r[0]}:{r[1]}".encode()).hexdigest()[:8], 16) / 0xffffffff < drop_share: continue
            n_fol += 1
        cv.apply(r)
    out = K / cv.vt - K / (cv.vt + mytok)
    pnl = (out - x_in) / 1e9 - FEE * (x_in + out) / 1e9 - FIXED
    return {"filled": True, "pnl": pnl, "fill_slot": fill[0], "n_fol": n_fol}
