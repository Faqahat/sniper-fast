#!/usr/bin/env python3
# EXIT STUDY shared library (read-only on all inputs). Corrected dip replay (= modelcheck/mc_corr.replay_corr with the
# corrections the model check validated: follow="comp", others="keep", phantom sells; our own wallets' trades removed from
# the tape as in recon/rsim.run_path) that keeps the WHOLE post-entry event stream, so any exit (slot timer, event trigger,
# learned policy) can be valued on the same path, with realistic sell landing:
#   - slot-tick decisions (the engine's time-limit style check at the first feed trade of a slot): the sell lands Ls ms after
#     the slot start; MEASURED row = our 107 live time-limit sells (deciles, median 94 ms, 10/107 spill into the next slot)
#   - event decisions (a trade on the token triggers the sell): the sell lands Ls ms after that trade (block-position clock);
#     MEASURED row = our 20 live stop-loss sells (median 42 ms)
#   - fixed rows 35 / 50 / 75 ms for both kinds.
# Clock: the replay's block-position clock (slot x 212 ms + idx / max(400, idx + 1) x 212 ms).
import os, sys, json, zlib, bisect, time, calendar
import numpy as np

SMS = 212.0; GRADV = 110e9; KMAX = 40
DATA = "/home/moiz/sniper-data/exits"
WAL = {"FRA": "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "AMS": "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
WAL_UID = {zlib.crc32(w.encode()) for w in WAL.values()}
TARGETS = [l.strip() for l in open("/home/moiz/sniper/ops/dip/modelcheck/targets.txt") if l.strip()]
COHORT = json.load(open("/home/moiz/sniper/ops/overnight/sel/cohort_train.json"))
U_TGT = {zlib.crc32(u.encode()) for u in TARGETS}
U_COH = {zlib.crc32(u.encode()) for u in COHORT} - U_TGT
CURVES = "/home/moiz/sniper-data/modelcheck/curves_all.json"
M2_BUNDLE = "/home/moiz/sniper-data/strategies/dipdetect/m2_v3_reg4_top25.json"
M2_THR = 0.010095262901162569
IMIT_THR4 = 0.21088520504965255
FIX = 0.0045          # our real all-in tx cost per round trip (owner: ~0.0045; nonce era measured 0.0027-0.0047)
FAIL = 0.000505       # failed (guard) buy, 5M priority (MEASURED)
SIZE = 0.35; GUARD = 1.05

# ---- measured landing (recon fires.json, 309 live fires, block-position ms after the dump), by leader client group
GROUPS = {"JitoLabs": "Jito", "AgaveBam": "BAM", "FireBAM": "BAM", "HarmonicAgave": "Harmonic", "HarmonicFiredancer": "HarmonicFD",
          "Firedancer": "FD", "Frankendancer": "FD", "Rakurai": "Rakurai"}
GI = {"Jito": 0, "BAM": 1, "Harmonic": 2, "HarmonicFD": 3, "FD": 4, "Rakurai": 5, "other": 6}


def pk(s):
    f = "%Y-%m-%d %H:%M:%S" if s.count(":") == 2 else "%Y-%m-%d %H:%M"
    return calendar.timegm(time.strptime("2026-" + s, f)) - 18000


def pkt(t, fmt="%m-%d %H:%M"):
    return time.strftime(fmt, time.gmtime(t + 5 * 3600))


def deciles(a):
    a = np.asarray(a, float)
    return np.percentile(a, np.arange(5, 100, 10))


def landing_tables():
    F = json.load(open("/home/moiz/sniper-data/recon/work/fires.json"))
    by = {}
    allL = []
    for r in F["rows"]:
        if r.get("L_meas") is None: continue
        g = GROUPS.get(r.get("client") or "", "other"); by.setdefault(g, []).append(r["L_meas"]); allL.append(r["L_meas"])
    tab = {g: deciles(v) for g, v in by.items()}
    tab["other"] = deciles(allL); tab["ALL"] = deciles(allL)
    return tab, {g: len(v) for g, v in by.items()}


def sell_latency_tables():
    """MEASURED sell landing: time-limit sells (ms after the start of the intended slot) and stop-loss sells (ms after the trigger)"""
    P = json.load(open("/home/moiz/sniper-data/recon/work/pertrade.json")); F = json.load(open("/home/moiz/sniper-data/recon/work/fires.json"))
    cfg = {(r["srv"], r["run"]): r["cfg"] for r in F["runs"]}
    tl = []
    for o in P:
        if not o["live_fill"] or o.get("sell_slot") is None or o.get("exit_why_live") == "stop-loss": continue
        h = cfg[(o["srv"], o["run"])]["hold_slots"]; tgt = o["land_slot"] + h - 1
        tl.append((o["sell_slot"] - tgt) * SMS + o["sell_idx"] / max(400, o["sell_idx"] + 1) * SMS)
    sl = json.load(open("/home/moiz/sniper-data/recon/work/sell_latency.json"))["sl_lat"]
    sl = [x for x in sl if x >= 1.0]        # 3 of 20 landed < 0.2 ms after the "trigger": the real trigger was an earlier trade (not a latency)
    return deciles(tl), deciles(sl), len(tl), len(sl)


# ---- leaders: slot -> leader id -> client group, near flags
class Leaders:
    def __init__(self):
        lb = json.load(open("/home/moiz/sniper/ops/overnight/dipshadow/leaders_book.json"))
        self.nodes = lb["nodes"]
        self.sc = []
        for f in ("/home/moiz/sniper/ops/dip/speed/leaders/schedule_cur.json", "/home/moiz/sniper-data/competitors2/schedule_1067.json"):
            s = json.load(open(f)); self.sc.append((s["start"], s["slot_leader"], s["ids"]))
        self.lb_leaders = lb["leaders"]
        rd = lambda p: {l.strip() for l in open(p) if l.strip()}
        self.near = {"FRA": rd("/home/moiz/sniper/ops/region/near_leaders_fra.txt"), "AMS": rd("/home/moiz/sniper/ops/region/near_leaders_ams.txt"),
                     "AMS_NOBAM": rd("/home/moiz/sniper/ops/region/near_leaders_ams_nobam.txt")}

    def leader(self, slot):
        for st, sl, ids in self.sc:
            o = slot - st
            if 0 <= o < len(sl): return ids[sl[o]]
        return self.lb_leaders.get(str(slot))

    def group(self, u):
        if u is None: return "other"
        return GROUPS.get((self.nodes.get(u) or {}).get("client") or "", "other")

    def arrays(self, slots):
        """per slot: group index, near FRA, near AMS, near AMS no-BAM (vectorised over unique slots)"""
        us, inv = np.unique(np.asarray(slots, np.int64), return_inverse=True)
        g = np.zeros(len(us), np.int8); nf = np.zeros(len(us), bool); na = np.zeros(len(us), bool); nb = np.zeros(len(us), bool); known = np.zeros(len(us), bool)
        for k, s in enumerate(us.tolist()):
            u = self.leader(s)
            known[k] = u is not None
            g[k] = GI[self.group(u)]; nf[k] = u in self.near["FRA"]; na[k] = u in self.near["AMS"]; nb[k] = u in self.near["AMS_NOBAM"]
        return g[inv], nf[inv], na[inv], nb[inv], known[inv]


# ---- follower tolerance curves (model check)
class Curves:
    def __init__(self, path=CURVES):
        C = json.load(open(path)); self.C = {}
        for k, v in C.items():
            if k == "_n": continue
            self.C[k] = (np.array(v[0], float), np.array(v[1], float))
        self.U = {zlib.crc32(k.split("|")[0].encode()): k.split("|")[0] for k in C if not k.startswith("_")}

    def S(self, w, p, cond=None):
        if cond is not None and f"{w}|{cond}" in self.C: key = f"{w}|{cond}"
        elif w in self.C: key = w
        elif cond is not None: key = f"_targets|{cond}"
        else: key = "_targets"
        cx, fy = self.C[key]
        return float(np.interp(p, cx, fy))


# ---- tape
class Tape:
    def __init__(self, tag):
        z = np.load(f"{DATA}/{tag}/day_{tag}.npz"); M = json.load(open(f"{DATA}/{tag}/day_{tag}_meta.json"))
        self.tag = tag
        self.c = {k: z[k] for k in ("tok", "s", "i", "arr", "buy", "sol", "tokn", "vsol", "vtok", "fr", "slack", "uid", "wt", "bt")}
        self.meta = M["meta"]
        nt = len(self.meta); cnt = np.bincount(self.c["tok"], minlength=nt)
        self.off = np.concatenate([[0], np.cumsum(cnt)[:-1]]).astype(np.int64); self.cnt = cnt
        uid = self.c["uid"]
        cls = np.zeros(len(uid), np.int8)
        cls[np.isin(uid, np.array(sorted(U_COH), np.int64))] = 2
        cls[np.isin(uid, np.array(sorted(U_TGT), np.int64))] = 1
        cls[self.c["wt"] == 1] = 3
        cls[np.isin(uid, np.array(sorted(WAL_UID), np.int64))] = 9
        self.c["cls"] = cls
        self._cache = {}

    def token(self, t):
        tp = self._cache.get(t)
        if tp is None:
            o = int(self.off[t]); n = int(self.cnt[t]); sl = slice(o, o + n)
            tp = {k: v[sl].tolist() for k, v in self.c.items()}
            tp["n"] = n; tp["o"] = o; tp["_S0"] = self.meta[t]["S0"]
            if len(self._cache) > 3000: self._cache.clear()
            self._cache[t] = tp
        return tp


def simulate(tp, j0, size=SIZE, L=None, at=None, guard=GUARD, CV=None, rowkey=0, kmax=KMAX, win_slots=3, phantom=True, crowd=0.0):
    """our buy after the dump at local index j0 (L block-position ms later, or at chain position at=(slot, idx)).
    Corrected model (model check): target fast bots behind us within the dump slot + win_slots keep with the measured tolerance
    ratio (conditional on a competitor ahead), other followers keep, dropped buyers do not sell phantom tokens later; our own
    wallets' trades are removed. Returns dict(st 0 fill / 1 guard fail / 2 untradeable, ratio, ahead, s_in, a_in, q, v0,
    ev = list of post-entry events (a, s, buy, sol_lamports, cls, uid, val_after, V_after) of APPLIED trades only)."""
    S = tp["s"]; A = tp["arr"]; B = tp["buy"]; SOL = tp["sol"]; TK = tp["tokn"]; V_ = tp["vsol"]; T_ = tp["vtok"]; FR = tp["fr"]
    U = tp["uid"]; CL = tp["cls"]; I = tp["i"]; n = tp["n"]; SK = tp["slack"]
    a0 = A[j0]; fr0 = float(FR[j0]); p_after = V_[j0] / T_[j0]
    V = float(V_[j0]); T = float(T_[j0]); removed = False
    j = j0 + 1; ahead = 0; tg_real = False; last_real = j0      # last tape row before our landing that is not our own trade
    lim = None if at is None else at[0] * 100000 + at[1]
    while j < n:
        if CL[j] == 9:
            removed = True; j += 1; continue
        if lim is None:
            if A[j] >= a0 + L: break
        elif S[j] * 100000 + I[j] >= lim: break
        if not removed:
            V = float(V_[j]); T = float(T_[j])
        else:
            if B[j]:
                dt = T * SOL[j] / (V + SOL[j]); V += SOL[j]; T -= dt
            else:
                so = V * TK[j] / (T + TK[j]); V -= so; T += TK[j]
        if B[j] and CV is not None and U[j] in CV.U: tg_real = True
        ahead += 1; last_real = j; j += 1
    ke = j
    ratio = (V / T) / p_after
    res = dict(ratio=ratio, ahead=ahead)
    if V >= 100e9: res["st"] = 2; return res
    if ratio > guard: res["st"] = 1; return res
    X = size * 1e9 / (1 + fr0); q = T * X / (V + X); V += X; T -= q
    if lim is None:
        s_land = int((a0 + L) // SMS); s_in = max(S[last_real], s_land); a_in = a0 + L     # (not S[ke - 1]: that row can be our own removed trade)
    else:
        s_in = at[0]; a_in = at[0] * SMS + at[1] / max(400, at[1] + 1) * SMS
    frs = fr0
    v0 = V * q / (T + q) * (1 - frs) / 1e9; V_entry = V
    s_dump = S[j0]; win_end = s_dump + win_slots; s_cut = s_in + kmax + 1
    ev = []; deficit = {}; tg_seen = tg_real
    prevV = float(V_[last_real]); prevT = float(T_[last_real])     # real recorded state before row j (for the tolerance ratio)
    cfrac = 0.0
    if crowd > 0:        # model check "+crowd": later (> 60 ms after the dump, slot <= s_in + 4) non-bot buys shrink by crowd x our SOL, pro rata
        fol = sum(SOL[x] for x in range(ke, n) if S[x] <= s_in + 4 and B[x] and A[x] - a0 > 60 and CL[x] != 9 and not (CV is not None and U[x] in CV.U))
        cfrac = min(1.0, crowd * X / fol) if fol > 0 else 0.0
    for j in range(ke, n):
        sj = S[j]
        if sj > s_cut: break
        c = CL[j]
        if c == 9: continue
        u = U[j]
        if B[j]:
            sol = SOL[j]
            if cfrac > 0 and sj <= s_in + 4 and A[j] - a0 > 60 and not (CV is not None and u in CV.U): sol = sol * (1 - cfrac)
            dt = T * sol / (V + sol)
            w = CV.U.get(u) if CV is not None else None
            if w is not None and sj <= win_end:
                p_real = (prevV / prevT) / p_after; p_mod = (V / T) / p_after
                kp = CV.S(w, p_mod, 1) / max(CV.S(w, p_real, 1 if tg_seen else 0), 1e-6)
                keep = ((zlib.crc32(f"{rowkey}:{j}".encode()) & 0xffffffff) / 2 ** 32) < min(1.0, kp)
            elif w is not None:
                keep = not (dt < TK[j] / (1.0 + SK[j]))          # fast bots after the tolerance window: the model's slack rule (as mc_corr)
            else:
                keep = True
            if w is not None: tg_seen = True
            prevV = float(V_[j]); prevT = float(T_[j])
            if not keep:
                if phantom: deficit[u] = deficit.get(u, 0.0) + TK[j]
                continue
            V += sol; T -= dt
            if phantom and dt < TK[j]: deficit[u] = deficit.get(u, 0.0) + (TK[j] - dt)
        else:
            prevV = float(V_[j]); prevT = float(T_[j])
            tk = TK[j]
            dfc = deficit.get(u, 0.0)
            if dfc > 0:
                cut = min(tk, dfc); deficit[u] = dfc - cut; tk -= cut
            if tk <= 0: continue
            sol = V * tk / (T + tk); V -= sol; T += tk
        frs = float(FR[j])
        ev.append((A[j], sj, B[j], sol, c, u, V * q / (T + q) * (1 - frs) / 1e9, V))
        if V >= GRADV: break
    res.update(st=0, s_in=s_in, a_in=a_in, q=q, v0=v0, ev=ev, s_dump=s_dump, size=size, V_in=V_entry)
    return res


def value_at(res, t):
    """position value (SOL, after the sell's pump fee) of a sell landing at block time t: every applied trade before t is ahead"""
    ev = res["ev"]
    # binary search on event times
    lo, hi = 0, len(ev)
    while lo < hi:
        m = (lo + hi) // 2
        if ev[m][0] < t: lo = m + 1
        else: hi = m
    return ev[lo - 1][6] if lo > 0 else res["v0"]


def tick_values(res, K, lsv):
    """V[k] for k = 0..K: mean sell value over the sell-landing offsets lsv (ms after the start of slot s_in + k); k = 0 unused"""
    s_in = res["s_in"]; out = np.zeros(K + 1)
    for k in range(1, K + 1):
        base = (s_in + k) * SMS
        out[k] = np.mean([value_at(res, base + x) for x in lsv])
    out[0] = res["v0"]
    return out


# ---- tick features (causal: only applied events in slots < s_in + k)
TF = ["k", "ms_in", "r", "r_peak", "r_dd", "r_d1", "r_d2", "r_d4", "bsol1", "ssol1", "bsol2", "ssol2", "bsol4", "ssol4", "bsol_e", "ssol_e",
      "nb1", "ns1", "nb2", "nb_e", "ns_e", "nbuyer_e", "tgb_e", "tgb2", "tgs_e", "cohb_e", "cohs_e", "bot_hold", "bot_hold_sol",
      "stall_slots", "stall_ms", "stall01_slots", "maxb2", "maxs2", "bigs_e", "dev_s_e", "vsol", "age_slots", "since_dump",
      "tg_dump", "coh_dump", "tg_hold"]
TFI = {k: i for i, k in enumerate(TF)}


def tick_features(res, tp, j0, K, pre_hold=None):
    """feature rows for ticks k = 1..K (decision at the start of slot s_in + k). pre_hold: bot holders (uid -> SOL) from the dump to
    our entry (computed by the caller on the real tape)."""
    ev = res["ev"]; s_in = res["s_in"]; size = res["size"]; v0 = res["v0"]; a_in = res["a_in"]
    S0 = tp["_S0"]; s_dump = res["s_dump"]
    out = np.zeros((K, len(TF)), np.float32)
    # running state
    bsol_e = ssol_e = 0.0; nb_e = ns_e = 0; buyers = set(); tgb_e = tgs_e = cohb_e = cohs_e = 0; bigs_e = 0; dev_s_e = 0.0
    pre_hold = pre_hold or ({}, set(), set())
    hold = dict(pre_hold[0])                          # bot uid -> SOL bought (still holding)
    tg_set = set(pre_hold[1]); coh_set = set(pre_hold[2])     # distinct target fast bots / cohort bots that bought since the dump
    tg_hold = {u for u in hold if u in tg_set}
    last_buy_a = None; last_buy_s = None; last_b01_s = None
    r_peak = v0 / size - 1; Vcur = None
    per_slot = {}                                      # slot -> [bsol, ssol, nb, ns, tgb, maxb, maxs]
    e = 0; ne = len(ev)
    r_hist = [v0 / size - 1]                           # r at tick boundaries: r_hist[k] = r just before tick k (k >= 1); r_hist[0] = entry
    cur_val = v0
    for k in range(1, K + 1):
        s = s_in + k; t = s * SMS
        while e < ne and ev[e][0] < t:
            a, sj, b, sol, c, u, val, Vv = ev[e]
            ps = per_slot.get(sj)
            if ps is None: ps = per_slot[sj] = [0.0, 0.0, 0, 0, 0, 0.0, 0.0]
            if b:
                bsol_e += sol; nb_e += 1; buyers.add(u); ps[0] += sol; ps[2] += 1
                if sol > ps[5]: ps[5] = sol
                last_buy_a = a; last_buy_s = sj
                if sol >= 0.1e9: last_b01_s = sj
                if c == 1: tgb_e += 1; ps[4] += 1; tg_set.add(u); tg_hold.add(u)
                elif c == 2: cohb_e += 1; coh_set.add(u)
                if c in (1, 2): hold[u] = hold.get(u, 0.0) + sol
            else:
                ssol_e += sol; ns_e += 1; ps[1] += sol; ps[3] += 1
                if sol > ps[6]: ps[6] = sol
                if sol >= 1e9: bigs_e += 1
                if c == 1: tgs_e += 1
                elif c == 2: cohs_e += 1
                elif c == 3: dev_s_e += sol
                if u in hold: del hold[u]
                tg_hold.discard(u)
            cur_val = val; Vcur = Vv
            r = val / size - 1
            if r > r_peak: r_peak = r
            e += 1
        r = cur_val / size - 1
        r_hist.append(r)
        row = out[k - 1]
        row[0] = k; row[1] = t - a_in; row[2] = r; row[3] = r_peak; row[4] = r_peak - r
        row[5] = r - r_hist[k - 1]; row[6] = r - r_hist[max(0, k - 2)]; row[7] = r - r_hist[max(0, k - 4)]
        w1 = per_slot.get(s - 1); w2 = per_slot.get(s - 2); w3 = per_slot.get(s - 3); w4 = per_slot.get(s - 4)
        g = lambda w, i: (w[i] if w is not None else 0.0)
        row[8] = g(w1, 0) / 1e9; row[9] = g(w1, 1) / 1e9
        row[10] = (g(w1, 0) + g(w2, 0)) / 1e9; row[11] = (g(w1, 1) + g(w2, 1)) / 1e9
        row[12] = (g(w1, 0) + g(w2, 0) + g(w3, 0) + g(w4, 0)) / 1e9; row[13] = (g(w1, 1) + g(w2, 1) + g(w3, 1) + g(w4, 1)) / 1e9
        row[14] = bsol_e / 1e9; row[15] = ssol_e / 1e9
        row[16] = g(w1, 2); row[17] = g(w1, 3); row[18] = g(w1, 2) + g(w2, 2); row[19] = nb_e; row[20] = ns_e; row[21] = len(buyers)
        row[22] = tgb_e; row[23] = g(w1, 4) + g(w2, 4); row[24] = tgs_e; row[25] = cohb_e; row[26] = cohs_e
        row[27] = len(hold); row[28] = sum(hold.values()) / 1e9
        row[29] = (s - last_buy_s) if last_buy_s is not None else (k + 0.5)
        row[30] = (t - last_buy_a) if last_buy_a is not None else (t - a_in)
        row[31] = (s - last_b01_s) if last_b01_s is not None else (k + 0.5)
        row[32] = max(g(w1, 5), g(w2, 5)) / 1e9; row[33] = max(g(w1, 6), g(w2, 6)) / 1e9
        row[34] = bigs_e; row[35] = dev_s_e / 1e9
        row[36] = (Vcur if Vcur is not None else res["V_in"]) / 1e9
        row[37] = s - S0; row[38] = s - s_dump
        row[39] = len(tg_set); row[40] = len(coh_set); row[41] = len(tg_hold)
    return out


def pre_holders(tp, j0, res):
    """target / cohort bots that bought between the dump and our landing (real tape) and still hold at our entry -> uid -> SOL"""
    S = tp["s"]; B = tp["buy"]; CL = tp["cls"]; U = tp["uid"]; SOL = tp["sol"]; A = tp["arr"]
    hold = {}; tg = set(); coh = set()
    # bots that bought between the dump and our landing (real tape; what our feed has seen at entry)
    t_in = res["a_in"]
    for j in range(j0 + 1, tp["n"]):
        if A[j] >= t_in: break
        c = CL[j]
        if c not in (1, 2): continue
        if B[j]:
            hold[U[j]] = hold.get(U[j], 0.0) + SOL[j]
            (tg if c == 1 else coh).add(U[j])
        elif U[j] in hold: del hold[U[j]]
    return hold, tg, coh


# ---- the M2 score of dd1 rows (the engine's bundle, scored the study's way)
def m2_scores(Xall):
    sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect")
    import dd20_shadow_eval as SH, dd_lib as DL
    B0 = json.load(open(M2_BUNDLE)); cols = [DL.FNI[f] for f in B0["fn"]]
    P, _ = SH.bundle_scores(M2_BUNDLE, Xall[:, cols])
    return P
