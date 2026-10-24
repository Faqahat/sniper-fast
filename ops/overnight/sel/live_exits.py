#!/usr/bin/env python3
# Exit grid shared by the live paper run (live_sim.py) and its backtest (sel_exitbt.py): take-profit x stop-loss x time limit,
# all evaluated on ONE replay of our position (held up to 60 slots, same follower model as the study builder).
# A TP / SL trigger sends the sell, which lands in the next slot (SELL_LAT ms in); else we sell at the time limit.
import numpy as np
TPS = (0.05, 0.08, 0.10, 0.15, 0.20, 0.30, 0.50, None)
SLS = (0.05, 0.10, 0.20, None)
SECS = (1.3, 2, 4, 6, 8, 12)
def name(tp, sl, sx): return f"tp{round(tp * 100) if tp else 'none'}_sl{round(sl * 100) if sl else 'none'}_{sx:g}s"
EXITS = [(name(tp, sl, sx), tp if tp else 9.0, sl if sl else 9.0, round(sx / 0.212), 1) for tp in TPS for sl in SLS for sx in SECS]
MAIN = "tp8_sl5_1.3s"
def label(n):
    tp, sl, t = n.split("_")
    return ("TP +" + tp[2:] + "%" if tp != "tpnone" else "no TP") + " / " + ("SL -" + sl[2:] + "%" if sl != "slnone" else "no SL") + " / " + t[:-1] + " s"
def detail(X, tr, k, L):
    """X = the selexit2 module. Entry L ms after the dump at trade k; 2% guard; returns {"f": 0} if skipped, else
    {"f": 1, exit_name: [pnl, why (T take-profit / S stop-loss / L time limit), hold seconds]}"""
    t = tr[k]; a0 = X.arr(t); fr = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4; p_after = t["vsol"] / t["vtok"]
    ke = k + 1
    while ke < len(tr) and X.arr(tr[ke]) < a0 + L: ke += 1
    if ke >= len(tr): return None
    if (tr[ke - 1]["vsol"] / tr[ke - 1]["vtok"]) / p_after > 1.02: return {"f": 0}
    s_land = int((a0 + L) // X.SMS)
    s_in, S_, K_, VAL, CHK, PNL = X.rt_path(tr, ke, fr, s_land)
    n = len(K_); out = {"f": 1}; HT = {}; HS = {}
    for nm, tp, sl, cap, mh in EXITS:
        if tp not in HT: HT[tp] = CHK & (VAL >= 1 + tp)
        if sl not in HS: HS[sl] = CHK & (VAL <= 1 - sl)
        co = s_in + cap; win = (S_ + 1 < co) & (S_ + 1 >= s_in + mh)
        ti = np.flatnonzero(HT[tp] & win); si = np.flatnonzero(HS[sl] & win)
        a = int(ti[0]) if len(ti) else None; b = int(si[0]) if len(si) else None
        if a is None and b is None: s_out, why = co, "L"
        elif b is None or (a is not None and a <= b): s_out, why = int(S_[a]) + 1, "T"
        else: s_out, why = int(S_[b]) + 1, "S"
        j = min(int(np.searchsorted(K_, 2 * s_out + 1, side="left")), n)
        out[nm] = [round(float(PNL[j]), 5), why, round((s_out - s_in) * 0.212, 2)]
    return out
