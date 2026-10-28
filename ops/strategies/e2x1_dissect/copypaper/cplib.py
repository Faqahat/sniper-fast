"""copypaper: tape from decoded chunks (cp_decode.py caches), block clock, signal extraction and the frozen copy-trade simulation.
Curve maths = ourspeed/o2_sim.py trip() (= sniper-haqqml/sim.py): constant product, our SOL kept in the curve until we sell,
pump fee f on the way in and out, entry/exit state = last recorded trade strictly before our landing position.
PumpSwap exits use grad/glib.py's effective-reserve rule (reserve derived from the trade amounts)."""
import json, os, datetime as dt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ME = "E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb"
SIB = "Grozoe2Lk9yu7kWPcCMuWEbrnuBYseBExkYAuHPRJUdJ"
CLUSTER = (ME, SIB)
SLOT_MS = 212.07
PKT = dt.timezone(dt.timedelta(hours=5))
def pkt(bt): return dt.datetime.fromtimestamp(int(bt), PKT).strftime("%m-%d %H:%M")

# ---- frozen strategy parameters (FROZEN.md) ----------------------------------------------------------------------
L_MS = 66.0            # our landing median after the signal is seen (buy) and after their sell is seen (sell)
CAP_SOL = 0.5          # our size = min(their cost, CAP)
GUARD = 1.05           # revert if we would get < qref/GUARD tokens (price +5% over the post-their-buy price)
TIMEOUT_S = 1800       # sell if they have not sold
STOP = 0.20            # variant: sell when our mark is 20% under cost
VSOL_LO, VSOL_HI = 25e9, 200e9
COST_TRIP, COST_REVERT = 0.0029e9, 0.0003e9     # lamports: per filled round trip / per reverted try
PHI = 0.2              # followers variant: remove 20% of other wallets' buy SOL between our entry and exit
FOLLOW_SLOTS = 10      # 'fast' follower variant (ourspeed's headline): only buys within 10 slots of our entry
def gap_lamports(S): return max(0.0, -4.4 + 28.1 * S) * 1e6   # calibrated: paper-vs-live gap per attempt (S in SOL)

_dq = json.load(open(os.path.join(HERE, "delay_q.json")))
Q_MS = np.array(_dq["q_pre"]); QMED = _dq["med_pre"]
D_SLOTS = Q_MS * (L_MS / QMED) / SLOT_MS      # 21 equiprobable landing delays, slot units
D2_SLOTS = D_SLOTS[::-1]                      # sell landing delay paired reversed (as o2_sim)
ND = len(D_SLOTS)

class Tape:
    """merged decoded chunks. T: curve trades of the mints of interest (sorted mint, slot, idx, j); P: PumpSwap events of
    those mints (sorted txmint, slot, idx, j); block clock over every recorded slot."""
    def __init__(self, files, keep_users=CLUSTER, keep_mints=None):
        files = sorted(files)
        strings = {}; sl = []
        trs = []; pss = []; migs = []; cmps = []; crs = []; metas = []
        # pass 1: id tables + which mints the cluster bought
        chunks = []
        for fn in files:
            Z = np.load(fn, allow_pickle=True)
            ids = Z["ids"]; g = np.empty(len(ids), np.int64)
            for k, s in enumerate(ids):
                v = strings.get(s)
                if v is None: v = strings[s] = len(strings)
                g[k] = v
            chunks.append((Z, g)); sl.append(Z["slots"]); metas.append(json.loads(str(Z["meta"][0])))
        self.strings = np.array(list(strings.keys()), dtype=object); self.sid = strings
        cl = {strings[w] for w in keep_users if w in strings}
        self.cluster_ids = cl
        want = set(keep_mints or ())
        want = {strings[m] for m in want if m in strings}
        if not keep_mints:
            for Z, g in chunks:
                tr = Z["tr"]
                if len(tr):
                    u = g[tr["user"]]; m = np.isin(u, list(cl)) & (tr["buy"] == 1)
                    want.update(np.unique(g[tr["mint"][m]]).tolist())
        wl = np.array(sorted(want), np.int64)
        for Z, g in chunks:
            tr = Z["tr"]
            if len(tr):
                mg = g[tr["mint"]]; k = np.isin(mg, wl)
                t = tr[k].copy(); t["mint"] = mg[k]; t["user"] = g[tr["user"][k]]; t["signer"] = g[tr["signer"][k]]; trs.append(t)
            ps = Z["ps"]
            if len(ps):
                mg = g[ps["txmint"]]; k = np.isin(mg, wl)
                p = ps[k].copy(); p["txmint"] = mg[k]; p["pool"] = g[ps["pool"][k]]; p["user"] = g[ps["user"][k]]; p["signer"] = g[ps["signer"][k]]; pss.append(p)
            for x in Z["mig"]: migs.append(json.loads(str(x)))
            for x in Z["cmp"]: cmps.append(json.loads(str(x)))
            for x in Z["cr"]: crs.append(json.loads(str(x)))
        self.T = np.concatenate(trs) if trs else np.zeros(0, chunks[0][0]["tr"].dtype)
        self.T.sort(order=["mint", "slot", "idx", "j"])
        self.P = np.concatenate(pss) if pss else np.zeros(0, chunks[0][0]["ps"].dtype)
        self.P.sort(order=["txmint", "slot", "idx", "j"])
        self.files = files; self.metas = metas
        # block clock
        S = np.concatenate(sl).astype(np.int64) if sl else np.zeros((0, 3), np.int64)
        self.slo = int(S[:, 0].min()); self.shi = int(S[:, 0].max())
        self.N = np.zeros(self.shi - self.slo + 2, np.int64); self.BT = np.zeros_like(self.N)
        np.maximum.at(self.N, S[:, 0] - self.slo, S[:, 2] + 1); np.maximum.at(self.BT, S[:, 0] - self.slo, S[:, 1])
        self.bt_lo = int(S[:, 1][S[:, 1] > 0].min()); self.bt_hi = int(S[:, 1].max())
        nz = np.nonzero(self.BT > 0)[0]; self.bt_slots = nz + self.slo; self.bt_vals = np.maximum.accumulate(self.BT[nz])
        # per-mint ranges
        mids = self.T["mint"].astype(np.int64)
        self.mint_list = np.unique(mids)
        self.ms = {int(m): (int(a), int(b)) for m, a, b in zip(self.mint_list, np.searchsorted(mids, self.mint_list, "left"), np.searchsorted(mids, self.mint_list, "right"))}
        pm = self.P["txmint"].astype(np.int64); pl = np.unique(pm)
        self.pms = {int(m): (int(a), int(b)) for m, a, b in zip(pl, np.searchsorted(pm, pl, "left"), np.searchsorted(pm, pl, "right"))}
        self.mig = {}
        for d in migs:
            if d.get("mig") and d["mint"] in strings and strings[d["mint"]] not in self.mig: self.mig[strings[d["mint"]]] = d
        self.cmp = {}
        for d in cmps:
            if d["mint"] in strings:
                k = strings[d["mint"]]
                if k not in self.cmp or (d["slot"], d["idx"]) < self.cmp[k]: self.cmp[k] = (d["slot"], d["idx"])
        self.mayhem = {strings[d["mint"]] for d in crs if d.get("mayhem") and d["mint"] in strings}
        self.created = {strings[d["mint"]]: d["bt"] for d in crs if d["mint"] in strings}
    def name(self, k): return str(self.strings[int(k)])
    # ---- block clock -------------------------------------------------------------------------------------------
    def bsize(self, s):
        k = np.clip(np.asarray(s, np.int64) - self.slo, 0, len(self.N) - 1); return self.N[k]
    def clock(self, s, i):
        n = self.bsize(s).astype(float); n[n <= 0] = 1
        return np.asarray(s, float) + np.minimum(np.asarray(i, float) / n, 0.999999)
    def position(self, t):
        t = np.asarray(t, float); s = np.floor(t).astype(np.int64); fr = t - s; n = self.bsize(s)
        for _ in range(12):
            miss = n <= 0
            if not miss.any(): break
            s = np.where(miss, s + 1, s); fr = np.where(miss, 0.0, fr); n = self.bsize(s)
        return s, np.floor(fr * np.maximum(n, 1)).astype(np.int64)
    def bt_of(self, s):
        k = int(s) - self.slo
        while 0 < k < len(self.BT) and self.BT[k] == 0: k -= 1
        return int(self.BT[max(min(k, len(self.BT) - 1), 0)])
    def slot_at_bt(self, bt):
        """first recorded slot whose block time >= bt (None if past the tape)"""
        k = int(np.searchsorted(self.bt_vals, bt, "left"))
        return int(self.bt_slots[k]) if k < len(self.bt_vals) else None
    # ---- rows --------------------------------------------------------------------------------------------------
    def rows(self, m):
        a, b = self.ms.get(int(m), (0, 0)); return self.T[a:b]
    def prows(self, m):
        a, b = self.pms.get(int(m), (0, 0)); return self.P[a:b]

def pos_key(s, i, j=0):
    return (np.asarray(s, np.int64) << 24) | (np.asarray(i, np.int64) << 4) | np.asarray(j, np.int64)

def before(keys, s, i):
    """index of the last row with key strictly before position (s, i); -1 if none"""
    return np.searchsorted(keys, pos_key(s, i), "left") - 1

# ---- PumpSwap pool state (grad/glib.py) -------------------------------------------------------------------------------
def q_eff(P, k):
    B, b, q, u = float(P["pbase"][k]), float(P["base"][k]), float(P["quote"][k]), float(P["uquote"][k])
    if b <= 0: return float(P["pquote"][k]) + 17.584e9
    if P["buy"][k] == 0: return q * (B + b) / b
    x = min(q, u); return B * x / b - x
def pool_state_after(P, k, mig):
    if k < 0: return float(mig["pbase"]), float(mig["pquote"])
    B, b = float(P["pbase"][k]), float(P["base"][k]); Q = q_eff(P, k)
    B2 = B + b if P["buy"][k] == 0 else B - b
    return B2, Q * B / B2
def pool_fee(P, k):
    if len(P) == 0: return 0.0125
    k = min(max(k, 0), len(P) - 1)
    for j in range(k, max(k - 50, -1), -1):
        if P["buy"][j] == 0 and P["quote"][j] > 0:
            return (float(P["lpfee"][j]) + float(P["pfee"][j]) + float(P["ccfee"][j])) / float(P["quote"][j])
    q = float(P["quote"][k])
    return (float(P["lpfee"][k]) + float(P["pfee"][k]) + float(P["ccfee"][k])) / q if q > 0 else 0.0125

# ---- signals ----------------------------------------------------------------------------------------------------------
def cluster_buys(tape, signal_users=None):
    """all successful curve buys by the cluster, in (mint, position) order: list of (mint_id, row index into tape.T)"""
    ids = tape.cluster_ids if signal_users is None else {tape.sid[w] for w in signal_users if w in tape.sid}
    T = tape.T
    m = np.isin(T["user"].astype(np.int64), list(ids)) & (T["buy"] == 1) & (T["sol"] > 0)
    return np.nonzero(m)[0]

def simulate(tape, kh, cfg, lockout=None):
    """one signal = cluster buy row kh (global index into tape.T). Returns a dict (expected values over the 21 draws) or None.
    cfg: dict(cap, guard, timeout, exit_users (set of user ids whose first sell exits us), stop, size='min'|'his', L)"""
    T = tape.T; r = T[kh]; mint = int(r["mint"])
    a, b = tape.ms[mint]; R = T[a:b]; kh_l = kh - a
    keys = pos_key(R["slot"], R["idx"], R["j"])
    f = (float(r["fbps"]) + float(r["cbps"])) / 1e4
    his_cost = float(r["sol"]) * (1 + f)
    S_l = min(his_cost, cfg["cap"] * 1e9) if cfg.get("cap") else his_cost
    x = S_l / (1 + f)
    S = S_l / 1e9
    sh, ih = int(r["slot"]), int(r["idx"])
    hb = float(tape.clock(np.array([sh]), np.array([ih]))[0])
    d = D_SLOTS * (cfg.get("L", L_MS) / L_MS); d2 = d[::-1]
    te = hb + d
    se, ie = tape.position(te)
    same = (se == sh) & (ie <= ih)
    n_h = max(int(tape.bsize(np.array([sh]))[0]), 1)
    te = np.where(same, sh + min((ih + 1) / n_h, 0.999999), te); se, ie = tape.position(te)
    ke = before(keys, se, ie); ke = np.maximum(ke, kh_l)
    Ve = R["vsol"][ke].astype(float); Te = R["vtok"][ke].astype(float); K = Ve * Te
    q = Te - K / (Ve + x)
    Vd, Td = float(r["vsol"]), float(r["vtok"]); qref = Td - Vd * Td / (Vd + x)
    fill = q >= qref / cfg.get("guard", GUARD)
    # ---- their first sell after the signal (curve or PumpSwap) ----
    exit_users = cfg["exit_users"]
    um = np.isin(R["user"].astype(np.int64), list(exit_users)) & (R["buy"] == 0)
    um[:kh_l + 1] = False
    ks = int(np.argmax(um)) if um.any() else -1
    sell_pos = (int(R["slot"][ks]), int(R["idx"][ks])) if ks >= 0 else None
    sell_kind = "copy"
    Pm = tape.prows(mint)
    if len(Pm):
        pm = np.isin(Pm["user"].astype(np.int64), list(exit_users)) & (Pm["buy"] == 0)
        pk = (Pm["slot"].astype(np.int64) > sh) | ((Pm["slot"].astype(np.int64) == sh) & (Pm["idx"].astype(np.int64) > ih))
        pm &= pk
        if pm.any():
            kp = int(np.argmax(pm)); pp = (int(Pm["slot"][kp]), int(Pm["idx"][kp]))
            if sell_pos is None or pp < sell_pos: sell_pos = pp; sell_kind = "ps"
    bt_h = int(r["bt"])
    timeout = cfg.get("timeout")
    kind = sell_kind
    if sell_pos is not None:
        hs = float(tape.clock(np.array([sell_pos[0]]), np.array([sell_pos[1]]))[0])
        if timeout and tape.bt_of(sell_pos[0]) > bt_h + timeout: sell_pos = None
    if sell_pos is None:
        if not timeout: return None            # (validation mode) no sell -> not a lot we can copy
        s_to = tape.slot_at_bt(bt_h + timeout)
        if s_to is None: s_to = tape.shi; kind = "unresolved"
        else: kind = "timeout"
        hs = float(s_to)
    tx = np.maximum(hs + d2, te)
    sx, ix = tape.position(tx)
    # curve complete before our exit? then the exit is on PumpSwap
    cmp = tape.cmp.get(mint); mig = tape.mig.get(mint)
    complete = np.zeros(ND, bool)
    if cmp is not None: complete = (sx > cmp[0]) | ((sx == cmp[0]) & (ix > cmp[1]))
    kx = before(keys, sx, ix); kx = np.maximum(kx, ke)
    last = len(R) - 1
    unresolved = (sx > tape.shi) | ((kx >= last) & (kind == "unresolved"))
    Vx = R["vsol"][kx].astype(float)
    fx = (R["fbps"][kx].astype(float) + R["cbps"][kx].astype(float)) / 1e4
    ob = np.where((R["buy"] == 1) & ~np.isin(R["user"].astype(np.int64), list(tape.cluster_ids)), R["sol"].astype(float), 0.0)
    cb = np.concatenate([[0.0], np.cumsum(ob)])
    kf = before(keys, *tape.position(np.minimum(tx, te + FOLLOW_SLOTS))); kf = np.maximum(np.minimum(kf, kx), ke)
    ball = cb[kx + 1] - cb[ke + 1]; bfast = cb[kf + 1] - cb[ke + 1]
    def curve_out(V2, fsell):
        V2 = np.maximum(V2, 1e6); return (V2 - K / (K / V2 + q)) * (1 - fsell)
    out0 = curve_out(Vx + x, fx); outf = curve_out(Vx + x - PHI * ball, fx); outff = curve_out(Vx + x - PHI * bfast, fx)
    # PumpSwap exit for draws whose exit is after the curve completed
    ps_used = False
    if complete.any():
        if mig is not None and mint in tape.pms:
            pk = pos_key(Pm["slot"], Pm["idx"], Pm["j"])
            for j in np.nonzero(complete)[0]:
                kpp = int(before(pk, sx[j], ix[j]))
                B, Qp = pool_state_after(Pm, kpp, mig); fee = pool_fee(Pm, kpp)
                o = Qp * q[j] / (B + q[j]) * (1 - fee)
                out0[j] = o; outf[j] = o; outff[j] = o; ps_used = True
        elif mig is not None:
            B, Qp = float(mig["pbase"]), float(mig["pquote"])
            o = Qp * q / (B + q) * (1 - 0.0125); out0 = np.where(complete, o, out0); outf = np.where(complete, o, outf); outff = np.where(complete, o, outff); ps_used = True
        else:
            # complete but no pool recorded yet: tokens are stuck at the completion price (conservative: last curve state)
            unresolved = unresolved | complete
    cost = x * (1 + f)
    pnl0 = np.where(fill, out0 - cost, 0.0); pnlf = np.where(fill, outf - cost, 0.0); pnlff = np.where(fill, outff - cost, 0.0)
    tc = np.where(fill, COST_TRIP, COST_REVERT)
    res = dict(mint=tape.name(mint), wallet=tape.name(r["user"])[:6], bt=bt_h, slot=sh, idx=ih, S=S, his_S=his_cost / 1e9, f=f,
               vsol_before=(Vd - float(r["sol"])) / 1e9, kind=kind, ps=ps_used, unresolved=float(unresolved.mean()),
               hold_s=float(np.mean((tx - te) * SLOT_MS / 1000)), fill=float(fill.mean()),
               raw=float((pnl0 - tc).mean()), f20=float((pnlf - tc).mean()), f20fast=float((pnlff - tc).mean()),
               cal=float((pnl0 - tc).mean() - gap_lamports(S)), gross=float(pnl0.mean()))
    # ---- stop variant: sell when the curve mark is STOP under cost (curve only, before the normal exit) ----
    if cfg.get("stop"):
        p0s = pnl0.copy(); pfs = pnlf.copy(); kinds = 0
        for j in range(ND):
            if not fill[j] or kx[j] <= ke[j]: continue
            seg = R["vsol"][ke[j] + 1:kx[j] + 1].astype(float)
            V2 = np.maximum(seg + x, 1e6); mark = (V2 - K[j] / (K[j] / V2 + q[j])) * (1 - fx[j])
            hit = np.nonzero(mark < (1 - cfg["stop"]) * cost)[0]
            if not len(hit): continue
            kst = ke[j] + 1 + int(hit[0])
            tst = float(tape.clock(np.array([R["slot"][kst]]), np.array([R["idx"][kst]]))[0]) + d2[j]
            if tst >= tx[j]: continue
            sxs, ixs = tape.position(np.array([tst])); kxs = max(int(before(keys, sxs, ixs)[0]), int(ke[j]))
            if cmp is not None and (sxs[0], ixs[0]) > cmp: continue      # past completion: keep the normal (PumpSwap) exit
            V2 = max(float(R["vsol"][kxs]) + x, 1e6); fs = (float(R["fbps"][kxs]) + float(R["cbps"][kxs])) / 1e4
            o = (V2 - K[j] / (K[j] / V2 + q[j])) * (1 - fs)
            bl = cb[kxs + 1] - cb[ke[j] + 1]; V2f = max(V2 - PHI * bl, 1e6); of = (V2f - K[j] / (K[j] / V2f + q[j])) * (1 - fs)
            p0s[j] = o - cost; pfs[j] = of - cost; kinds += 1
        res.update(raw_stop=float((p0s - tc).mean()), f20_stop=float((pfs - tc).mean()), cal_stop=float((p0s - tc).mean() - gap_lamports(S)),
                   stop_rate=kinds / ND)
    # lockout for re-entry: median-draw exit clock
    res["exit_clock"] = float(np.median(tx))
    res["entry_clock"] = float(np.median(te))
    return res

def run_window(tape, start_bt, end_bt, cfg, lockouts=None, signal_users=None):
    """score every signal with start_bt <= bt < end_bt. lockouts: dict mint -> exit clock (carried across windows). Returns rows."""
    lock = dict(lockouts or {}); rows = []
    idx = cluster_buys(tape, signal_users)
    T = tape.T
    for kh in idx:
        r = T[kh]; bt = int(r["bt"]); mint = int(r["mint"]); mn = tape.name(mint)
        if bt < start_bt or bt >= end_bt: continue
        pos = float(tape.clock(np.array([r["slot"]]), np.array([r["idx"]]))[0])
        if cfg.get("lockout", True) and lock.get(mn, -1) > pos: continue
        if cfg.get("band", True):
            vb = float(r["vsol"]) - float(r["sol"])
            if not (VSOL_LO <= vb <= VSOL_HI) or mint in tape.mayhem: continue
        res = simulate(tape, int(kh), cfg)
        if res is None: continue
        if cfg.get("lockout", True): lock[mn] = max(lock.get(mn, -1), res["exit_clock"])
        rows.append(res)
    # drop stale lockouts (exit clock before the window's first slot)
    s0 = tape.slot_at_bt(end_bt) or tape.shi
    lock = {m: c for m, c in lock.items() if c > s0}
    return rows, lock

def frozen_cfg():
    return dict(cap=CAP_SOL, guard=GUARD, timeout=TIMEOUT_S, stop=STOP, lockout=True, band=True, L=L_MS, exit_users=None)

def summarize(rows, lam=1e9):
    """window aggregate from per-signal rows (values in SOL)"""
    g = lambda k: sum(r.get(k, 0.0) for r in rows) / lam
    n = len(rows); fills = sum(r["fill"] for r in rows)
    out = dict(signals=n, fills=round(fills, 1), raw=g("raw"), f20=g("f20"), f20fast=g("f20fast"), cal=g("cal"),
               raw_stop=g("raw_stop"), f20_stop=g("f20_stop"), cal_stop=g("cal_stop"),
               timeouts=sum(1 for r in rows if r["kind"] == "timeout"), ps_exits=sum(1 for r in rows if r["ps"]),
               unresolved=sum(1 for r in rows if r["unresolved"] > 0), size_sol=sum(r["S"] for r in rows))
    for w in ("E2x1ew", "Grozoe"):
        rr = [r for r in rows if r["wallet"] == w]
        out[f"n_{w[:4]}"] = len(rr); out[f"raw_{w[:4]}"] = sum(r["raw"] for r in rr) / lam; out[f"cal_{w[:4]}"] = sum(r["cal"] for r in rr) / lam
        out[f"f20_{w[:4]}"] = sum(r["f20"] for r in rr) / lam
    srt = sorted((r["raw"] for r in rows), reverse=True)
    top5 = sum(srt[:5]) / lam; tot = out["raw"]
    out["top5_raw"] = top5; out["top5_share"] = (top5 / tot) if tot > 0 else None
    for k in ("raw", "f20", "cal"):
        s = sorted((r[k] for r in rows), reverse=True); out[f"{k}_ex_top5"] = (sum(s) - sum(s[:5])) / lam
    return out
