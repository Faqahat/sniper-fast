#!/usr/bin/env python3
# MODEL CHECK shared library (read-only on the study data). Loader for the day arrays + a replay engine that mirrors
# ops/strategies/dipdetect/dd1_build.py path() EXACTLY in its default mode (verified by mc_selftest.py against the stored
# dd1_<day>*.npz outputs), plus the extra modes this check needs:
#   - insert "ours" right before a given tape index (identity: replace a real bot's buy at its real landing spot),
#   - remove trades from the tape (the bot's own buy, and the part of its sells that closed the lot),
#   - sell at given tape indices (the bot's real sells) instead of / besides the exit grid,
#   - sell in a given slot at a given ms into the slot (exit-landing check),
#   - a pluggable follower rule (default = the model's: drop a buy if its tokens < real tokens / (1 + slack)).
import os, json, zlib
import numpy as np
PO = "/home/moiz/sniper-data/strategies/patterns"; DDD = "/home/moiz/sniper-data/strategies/dipdetect"
DAYS = {"R1": PO, "R2": PO, "R3": PO, "R4": DDD}
SMS = 212.0; SELL_LAT = 75.0; HMAX = 40; GRADV = 110e9
CAPS = (2, 4, 6, 9, 12, 19, 28, 38); TPS = (None, 0.05, 0.10, 0.20, 0.40); SLS = (None, 0.05, 0.10, 0.20, 0.30)
EXITS = [(c, tp, sl) for c in CAPS for tp in TPS for sl in SLS]
EXN = [f"c{c}_tp{'none' if tp is None else round(tp * 100)}_sl{'none' if sl is None else round(sl * 100)}" for c, tp, sl in EXITS]
EXI = {k: i for i, k in enumerate(EXN)}
E4 = EXI["c4_tpnone_slnone"]; E6 = EXI["c6_tpnone_sl10"]
OUT = "/home/moiz/sniper-data/modelcheck"
T3 = ["HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ", "DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw", "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"]
SEL = "/home/moiz/sniper/ops/overnight/sel"
COH = json.load(open(f"{SEL}/cohort_train.json"))
UPRO = {zlib.crc32(u.encode()) for u in T3} | {zlib.crc32(u.encode()) for u in COH}

def load_day(day):
    z = np.load(f"{DAYS[day]}/day_{day}.npz"); M = json.load(open(f"{DAYS[day]}/day_{day}_meta.json"))
    d = {k: z[k] for k in z.files if k != "F"}
    FI = {k: i for i, k in enumerate(M["feats"])}
    d["move"] = z["F"][:, FI["move"]].astype(np.float64); d["age"] = z["F"][:, FI["age"]].astype(np.float64)
    d["meta"] = M["meta"]
    nt = len(M["meta"]); cnt = np.bincount(d["tok"], minlength=nt); off = np.concatenate([[0], np.cumsum(cnt)[:-1]]).astype(np.int64)
    d["off"] = off; d["cnt"] = cnt
    return d

class Tape:
    __slots__ = ("S", "A", "B", "SOL", "TK", "V", "T", "FR", "SK", "U", "I", "n", "o")
    def __init__(self, d, t):
        o = int(d["off"][t]); n = int(d["cnt"][t]); sl = slice(o, o + n)
        self.o = o; self.n = n
        self.S = d["s"][sl].tolist(); self.A = d["arr"][sl].tolist(); self.B = d["buy"][sl].astype(bool).tolist()
        self.SOL = d["sol"][sl].tolist(); self.TK = d["tokn"][sl].tolist(); self.V = d["vsol"][sl].tolist(); self.T = d["vtok"][sl].tolist()
        self.FR = d["fr"][sl].astype(float).tolist(); self.SK = d["slack"][sl].astype(float).tolist(); self.U = d["uid"][sl].tolist()
        self.I = d["i"][sl].tolist()

def model_keep(tp, j, V, T, sol, dt):
    """the model's follower rule (dd1 path): keep the buy unless its tokens fall below real tokens / (1 + slack)"""
    return not (dt < tp.TK[j] / (1.0 + tp.SK[j]))

def replay(tp, j0, size=0.55, L=None, j_ins=None, Xc=None, fr_in=None, guard=1.05, rm=None, keep=model_keep,
           real_sells=None, slot_sells=None, s_in_force=None, want_grid=True, hmax=HMAX):
    """our buy after the dump at local index j0.
    placement: L (ms, block-position clock, as path()) or j_ins (insert right before local index j_ins).
    size: gross SOL (fees included) as path(); or Xc = SOL to the curve (overrides size; gross = Xc * (1 + fr_in)).
    rm: {local idx: None (drop the trade) | tokens (remove that many tokens from a sell row)}.
    real_sells: [(local idx, fraction of our tokens)]: we sell those fractions right before those rows (pro rata with the row's
      remaining tokens when the row also sells other tokens) -> 'real_exit' proceeds (SOL, after pump fee).
    slot_sells: [(slot, ms into slot, fraction)]: sells at a slot position (exit-landing check) -> 'slot_exit' proceeds.
    Returns dict(status 0 fill / 1 guard / 2 untradeable, ratio, ahead, s_in, q, cost, pnl[NEX] (as path: SOL P&L incl. pump fees,
      no fixed costs), off[NEX], real_exit, slot_exit, dropped (list of follower idx dropped), ent_px)."""
    S, A, Bb, SOL, TK, V_, T_, FR = tp.S, tp.A, tp.B, tp.SOL, tp.TK, tp.V, tp.T, tp.FR
    n = tp.n; rm = rm or {}
    assert not (want_grid and (real_sells or slot_sells)), "grid and real/slot sells need separate calls"
    a0 = A[j0]; fr0 = FR[j0]; p_after = V_[j0] / T_[j0]
    if j_ins is None:
        ke = j0 + 1
        while ke < n and A[ke] < a0 + L: ke += 1
        s_land = int((a0 + L) // SMS)
    else:
        ke = j_ins; s_land = S[j_ins] if j_ins < n else S[n - 1]
    # state before our buy: last trade before ke that is not removed (removed rows before ke are not supported -> assert)
    for x in rm:
        assert x >= ke, "removed rows must be at/after our insertion"
    ahead = ke - j0 - 1
    Vb = V_[ke - 1]; Tb = T_[ke - 1]
    ratio = (Vb / Tb) / p_after
    res = dict(status=0, ratio=ratio, ahead=ahead, ke=ke)
    if Vb >= 100e9: res["status"] = 2; return res
    if guard is not None and ratio > guard: res["status"] = 1; return res
    if Xc is None:
        X = size * 1e9 / (1 + fr0); cost = size
    else:
        X = Xc; cost = Xc * (1 + (fr_in if fr_in is not None else fr0)) / 1e9
    q = Tb * X / (Vb + X); V = Vb + X; T = Tb - q
    s_in = max(S[ke - 1], s_land) if s_in_force is None else s_in_force
    frs = fr0
    res.update(q=q, cost=cost, s_in=s_in, ent_px=cost * 1e9 / q)
    # ---------------- exit grid, exactly as path() ----------------
    NEX = len(EXITS)
    cur = V * q / (T + q) * (1 - frs) / 1e9 - cost
    poff = [None] * (hmax + 2); dn = 0
    ftp = [None] * len(TPS); fsl = [None] * len(SLS)
    s_cut = s_in + hmax + 1
    rs = sorted(real_sells or []); ri = 0; real_exit = 0.0; left = q      # real sells (pro rata within their row)
    ss = sorted(slot_sells or []); si = 0; slot_exit = 0.0
    dropped = []
    grid_done = not want_grid
    last_needed = max([x[0] for x in rs] or [-1])
    last_slot_needed = max([x[0] for x in ss] or [-1])
    for j in range(ke, n):
        sj = S[j]; pos = A[j] - sj * SMS
        if not grid_done:
            kj = 2 * sj + (1 if pos >= SELL_LAT else 0)
            while dn <= hmax + 1 and 2 * (s_in + dn) + 1 <= kj: poff[dn] = cur; dn += 1
            if sj > s_cut or dn > hmax + 1: grid_done = True
        # slot sells (exit landing check): sell before the first trade at/after (slot, ms)
        while si < len(ss) and (sj > ss[si][0] or (sj == ss[si][0] and pos >= ss[si][1])):
            qs = ss[si][2] * q; so = V * qs / (T + qs); slot_exit += so * (1 - frs) / 1e9; V -= so; T += qs; si += 1
        if grid_done and ri >= len(rs) and si >= len(ss): break
        applied = True
        rmv = rm.get(j, 0.0) if j in rm else 0.0
        if j in rm and rm[j] is None: applied = False
        elif Bb[j]:
            sol = SOL[j]; dt = T * sol / (V + sol)
            if not keep(tp, j, V, T, sol, dt): applied = False; dropped.append(j)
            else: V += sol; T -= dt
        else:
            tk = TK[j] - rmv
            # our real sells at this row: pro rata with the row's own remaining tokens
            our = 0.0
            while ri < len(rs) and rs[ri][0] == j: our += rs[ri][1] * q; ri += 1
            tot = tk + our
            if tot > 0:
                so = V * tot / (T + tot)
                if our > 0: real_exit += so * (our / tot) * (1 - FR[j]) / 1e9
                V -= so; T += tot
            else: applied = False
        if applied: frs = FR[j]
        if not grid_done:
            cur = V * q / (T + q) * (1 - frs) / 1e9 - cost
            if V >= GRADV: grid_done = True
            elif applied:
                val = (cur + cost) / cost
                for a in range(1, len(TPS)):
                    if ftp[a] is None and val >= 1 + TPS[a]: ftp[a] = sj
                for b in range(1, len(SLS)):
                    if fsl[b] is None and val <= 1 - SLS[b]: fsl[b] = sj
        if grid_done and ri >= len(rs) and si >= len(ss): break
    # anything not yet sold at the end of the tape: value at the last state
    while ri < len(rs):
        qs = rs[ri][1] * q; so = V * qs / (T + qs); real_exit += so * (1 - frs) / 1e9; V -= so; T += qs; ri += 1
    while si < len(ss):
        qs = ss[si][2] * q; so = V * qs / (T + qs); slot_exit += so * (1 - frs) / 1e9; si += 1
    if want_grid:
        while dn <= hmax + 1: poff[dn] = cur; dn += 1
        pn = [0.0] * NEX; of = [0] * NEX
        for e, (c, tp_, sl_) in enumerate(EXITS):
            co = s_in + c; a = ftp[TPS.index(tp_)] if tp_ is not None else None; b = fsl[SLS.index(sl_)] if sl_ is not None else None
            if a is not None and a + 1 >= co: a = None
            if b is not None and b + 1 >= co: b = None
            if a is None and b is None: so_ = co
            elif b is None: so_ = a + 1
            elif a is None: so_ = b + 1
            else: so_ = min(a, b) + 1
            dd = so_ - s_in; pn[e] = poff[dd]; of[e] = dd
        res["pnl"] = pn; res["off"] = of
    res["real_exit"] = real_exit; res["slot_exit"] = slot_exit; res["dropped"] = dropped
    return res
