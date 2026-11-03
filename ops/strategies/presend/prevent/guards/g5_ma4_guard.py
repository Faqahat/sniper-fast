#!/usr/bin/env python3
"""GUARDS step 5 = a COPY of multiarm/ma4_sim.py (unchanged except the marked GUARD lines): re-arm windows get the holder guard
(GUARD env: "off" | "open" | "naive" | "dumpZ" = the dump seller's balance at landing < Z% of supply): a re-arm try fills only if NO wallet but ours holds >= 6% of supply at its landing position
(abs bar, all holders on the chain at that point); "naive" also blocks it with p = 0.39 when a holder that was >= 6% at signing
sold out between signing and landing (its token account may be closed: MEASURED 39% of full big sells close it).
MULTIARM step 4: the JOINT try-level replay of one run under a re-arm rule variant (INFERRED, phantom tries; inputs MEASURED).

Every pre-send window of the run in one time-ordered event loop, as the dip26 engine runs them:
  * T2 windows: the run's live-armed T2 windows (arm at the trigger, first try +51 ms, their own stop rules: custom37 c37lib
    stop_times); a T2 trigger is blocked while our position / its 300 ms margin / our token account is open on the token; it takes
    an armed re-arm window's token over ("superseded").
  * re-arm windows: the rule's candidates on the tape (ma_lib port, checked vs live: ma2_validate), holders check at the first tx
    of slot dump+3 (+ the measured arm lateness), skipped when a window is armed on the token, the launch is not vanilla, or the
    per-token cap is reached; WAIT while our position / margin / token account / an earlier window's attempts can still land on
    the token (its stops run meanwhile: next big sell, no holder, its last slot, a T2 arm); the window's own end = ma_lib.natural_end
    (+ the measured end lateness); chained re-arm (rule.chain): after our position on the token closes, if a holder remains.
  * the SENDER: one tick per 26.5 ms per armed window (k 8 / slot); the one-position pause (every window, while any position is
    open: fill seen -> close); the rolling 24 h failed-try fee budget (1 SOL) pause; the route alternation (n + w) % 2 over
    helius-ps / astralane-ps and the three caps (route entry 40/s burst 10, global 60/s burst 15, path [[send]] budget H 40 / A 19
    in any rolling second: ops/lanes/astra_rate.py = pslive.rs take_rate).
  * a sent try: signed on the latest state seen, lands L ms later on the block clock (L drawn from the run's real landed tries,
    unseen share kept), fills iff it lands by its deadline (send slot + 1, <= the window's last slot) and the curve before its
    landing gives >= its min-out (presend_live limit_min_out at drop 0.12). The first filling try in chain order is the fill; it is
    seen at its landing; every other landed try is a failed try (5,120 lamports).
  * the position: c37lib exit_walk (200 ms timer + measured lateness, 2-slot backstop, TP 20 / SL 20 on trades seen), the sell lands
    D ms after the decision (D drawn from the run's live sells), closed C ms later; our token account counts as open until
    ata_clear ms after the sell's landing (MEASURED: live re-arm windows that waited on it armed a median 2.3 s after our sell).
P&L: cash = SOL back after pump's fee - size - 2.015 mSOL (tip, fees, sell tip, ATA rent net of its refund; MEASURED r37)
     - 5,120 lamports per landed failed try. Follower adjustment (paper audit pa9): + (slip - naive) on the clean tape (a follower
     buy whose min-out our buy breaks is dropped: the slack table); the -20% row also drops 20% of the remaining follower buys.
usage: ma4_sim.py CTX.pkl RULE_JSON REP OUT.pkl"""
import sys, json, pickle, math, heapq, bisect, collections, hashlib
from collections import deque
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/custom37")
sys.path.insert(0, "/home/moiz/sniper/ops/obs/paper_audit")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/multiarm")
import c37lib as L
import os
GUARD = os.environ.get('GUARD', 'off')
PCLOSE = 0.39
import pa_lib as PA
import ma_lib as M
from ma3_ctx import tape_rows, prep_live

SMS = 212.0
FAIL = 5120
FIX = L.FIX
MARGIN = 300.0
BUDGET = 1_000_000_000
ROUTES = ("helius-ps", "astralane-ps")


class Bucket:
    """send/budget.rs TokenBucket (ms clock)"""
    def __init__(self, rate, burst):
        self.rate = rate / 1e3; self.cap = float(burst); self.units = float(burst); self.last = None
    def _at(self, now): return self.units if self.last is None else min(self.cap, self.units + max(0.0, now - self.last) * self.rate)
    def peek(self, now): return self._at(now) >= 1.0 - 1e-12
    def take(self, now):
        self.units = self._at(now)
        if self.last is None or now > self.last: self.last = now
        self.units -= 1.0


class Window1s:
    """send/budget.rs Budget::try_now: at most n sends in any rolling second (ms clock)"""
    def __init__(self, n): self.n = n; self.q = deque()
    def try_now(self, now):
        while self.q and now - self.q[0] >= 1000.0: self.q.popleft()
        if len(self.q) >= self.n: return False
        self.q.append(now); return True


class Caps:
    def __init__(self, G=60, P=40, C=(40, 19)):
        self.g = Bucket(G, max(G // 4, 1)); self.p = [Bucket(P, max(P // 4, 1)) for _ in ROUTES]; self.c = [Window1s(c) for c in C]
    def ok(self, t, ri):
        if not self.p[ri].peek(t): return False
        if not self.g.peek(t): return False
        if not self.c[ri].try_now(t): return False
        self.p[ri].take(t); self.g.take(t)
        return True


class RObj:
    pass


class World:
    """everything a replay of one run needs, loaded once per worker"""
    def __init__(self, ctxp):
        ctx = pickle.load(open(ctxp, "rb"))
        self.ctx = ctx; self.run = ctx["run"]; self.cal = ctx["cal"]
        self.tape = M.Tape(ctx["tab"])
        X = pickle.load(open(ctx["xp"], "rb"))
        self.X = X
        self.A = M.Anchor(self.tape, X["trade_obs"]); self.B = M.Anchor(self.tape, X["land_obs"])
        R = RObj()
        for k, v in ctx["R"].items(): setattr(R, k, v)
        self.R = R
        lc = X["cfg"]["presend_live"]
        self.lc = lc
        self.allow_holder = bool(X["cfg"].get("allow_holder"))
        q = (lc.get("quiet") or {}).get("stop")
        self.cfg_t2 = dict(L.BASE, drop=lc["drop"], size=lc["spend"] / 1e9, k=lc["k"], win=lc["window_slots"], dl=lc["deadline_slots"], exit_ms=lc.get("exit_ms") or 10 ** 9,
                           exit_slots=lc["exit_slots"], tp=lc["tp"], sl=lc["sl"], qstop=tuple(int(v) for v in q.split(":")) if q else None, cut=0.0, flat=None)
        self.cfg_re = dict(self.cfg_t2, size=0.65, qstop=None)
        # T2 windows (live armed, inside the evaluation span), with the B-based clock anchor
        keys = set(map(tuple, ctx["live_keys"]))
        self.t2 = []
        for W in X["wins"]:
            if W["kind"] != "t2" or ("t2", W["w"]) not in keys: continue
            P = prep_live(self.tape, W)
            if P is None: continue
            self.anchor(P)
            P.live_exit_slots = lc.get("exit_slots") or 2; P.live_exit_ms = lc.get("exit_ms") or 10 ** 9
            self.t2.append(P)
        self.t2.sort(key=lambda P: P.t_trig)
        # the slot clock: first-tx time of every tape slot (feed ms)
        sl = self.tape.slots
        self.slot_t = np.array([self.tape.slot_start_cc(int(s)) + self.A(int(s)) for s in sl.tolist()])
        self.slot_t = np.maximum.accumulate(self.slot_t)
        self.t_start, self.t_end = self.cal["t_start"], self.cal["t_end"]
        self.s_start = int(sl[np.searchsorted(self.slot_t, self.t_start)])
        self._P = {}; self._recs = {}; self._launch = {}
        self.ata_dsl = np.array(self.cal["ata_dslots"])
        self.ata_clear = np.array(self.cal.get("ata_clear_ms") or [2320.0])

    def anchor(self, P):
        P.off = self.B(P.s0) + self.cal["own_vs_B"]
        P.off_s = P.off + self.cal["offs_rel"]
        P.off_est = "B"

    def slot_at(self, t):
        k = int(np.searchsorted(self.slot_t, t, side="right")) - 1
        return int(self.tape.slots[max(k, 0)])

    def seen(self, tl, k): return tl.c[k] + self.A(int(tl.s[k]))

    def first_seen_ge(self, tl, t):
        """the first trade of the token seen at or after t (feed ms)"""
        if tl.n == 0: return 0
        a = self.A(self.slot_at(t))
        k = int(np.searchsorted(tl.c, t - a - 400.0))
        while k < tl.n and self.seen(tl, k) < t: k += 1
        return k

    def launch_refusal(self, mint):
        v = self._launch.get(mint)
        if v is None:
            c = self.tape.creates.get(mint) or {}
            if not c: v = "no_launch_accounts"
            elif not c.get("v2"): v = "legacy_create"
            elif c.get("mayhem") or c.get("mayhem_ix"): v = "mayhem"
            else:
                van = (c.get("cfee_bps") or 0) == 0 and not c.get("holder") and not c.get("cashback")
                hold_ok = self.allow_holder and c.get("holder") and not c.get("cashback") and (c.get("cfee_bps") or 0) == 0
                v = "" if (van or hold_ok) else "non_vanilla"
            self._launch[mint] = v
        return v or None

    def window_P(self, mint, tl, k, key, en_slot, spend):
        """a c37lib window whose trigger is the token's trade k (a dump, or the last trade before a chained arm)"""
        P = self._P.get(key)
        if P is not None: return P
        s, i, j = int(tl.s[k]), int(tl.i[k]), int(tl.j[k])
        tg = {"sig": key[0] + str(k), "slot": s, "idx": i, "j": j, "t": self.seen(tl, k) * 1e6, "a": M.SMS * s, "wallet": self.tape.ids[int(tl.user[k])], "bal": 0,
              "vsol": int(tl.vsol[k]), "vtok": int(tl.vtok[k]), "age_slots": None, "mint": mint, "sol": int(tl.sol[k]), "tok": int(tl.tok[k]), "pct": None}
        W = {"run": self.run, "ses": 0, "w": key, "kind": "rearm", "mint": mint, "trig": tg, "en_slot": en_slot, "k": 8, "spend": spend, "drop": 0.12, "quiet": None,
             "dis": None, "tries": [], "fills": [], "exit": None, "sells": [], "close": None, "real": [], "late": [], "ptape": []}
        rows = tape_rows(self.tape, mint, s)
        P = L.prep_window(W, rows, self.tape.cc)
        if P is None: return None
        P.cc = self.tape.cc
        maxi = self.tape.maxi
        def pos_of(c, maxi=maxi):
            s_ = int(c // L.SMS); m_ = maxi.get(s_, 400) + 1.0
            return s_, int(min(m_ - 1, max(0, (c - s_ * L.SMS) / L.SMS * m_)))
        P.pos_of = pos_of; P.rx_map = {}
        self.anchor(P)
        P.live_exit_slots = 2; P.live_exit_ms = 10 ** 9
        self._P[key] = P
        return P

    def recs(self, mint):
        r = self._recs.get(mint)
        if r is None:
            t = self.tape.trades(mint)
            r = [] if t is None else PA.build_recs(t, self.tape.ours, drop_ours=True)
            self._recs[mint] = r
        return r

    def candidates(self, rule):
        """the rule's candidates inside the evaluation span (tape only), sorted by check time; skip counts"""
        out = []; skips = collections.Counter()
        need_tok = rule.trig_tok if rule.trig_sol is None else None
        T = self.tape.T
        sell = (T["buy"] == 0)
        if need_tok is not None: big = sell & (T["tok"] >= need_tok)
        else: big = sell & (T["sol"] >= int(rule.trig_sol * 1e9))
        mints = set(T["mint"][big].tolist())
        for g in mints:
            m = self.tape.ids[g]
            c = self.tape.creates.get(m)
            if not c or c["slot"] < self.s_start: continue
            tl = self.tape.tok(m)
            for cd in M.candidates(self.tape, tl, rule, self.A, self.s_start):
                k = cd["k"]
                t_dump = self.seen(tl, k)
                if not (self.t_start <= t_dump <= self.t_end): continue
                if cd["skip"]: skips[cd["skip"]] += 1; continue
                cd["mint"] = m; cd["t_chk"] = cd["t_check"] + self.cal["arm_dt"]; cd["en_slot"] = int(tl.s[k]) + M.WAIT + rule.gap
                cd["key"] = (m, int(tl.s[k]), int(tl.i[k]), int(tl.j[k])); cd["chained"] = False
                out.append(cd)
        out.sort(key=lambda c: c["t_chk"])
        return out, skips


class WinSt:
    __slots__ = ("wid", "key", "kind", "mint", "P", "size", "drop", "en", "t0", "t_stop", "why_stop", "n", "sent", "refused", "paused", "landed", "best", "bver",
                 "stopped", "end_t", "end_why", "last_dl", "rng", "cand", "nth", "t_arm", "filled", "res")


def rng_for(rep, *key):
    h = hashlib.blake2b(repr((rep,) + key).encode(), digest_size=8).digest()
    return np.random.default_rng(int.from_bytes(h, "little"))


def value_cut(recs, m_idx, size, stop, maxi, cut, rng):
    """pa_lib.value_at (slip on) with a share `cut` of the remaining follower buys dropped too -> gross SOL"""
    m = recs[m_idx]
    vb, tb, fr0 = float(m.vsol), float(m.vtok), m.fr
    if vb >= PA.UNTRADE_V: return None
    x = size * 1e9 / (1.0 + fr0); q = tb * x / (vb + x)
    v, t, frs = vb + x, tb - q, fr0
    for r in recs[m_idx + 1:]:
        if PA.cc_of(maxi, r.s, r.i) >= stop: break
        if r.buy:
            sol = float(r.sol); dt = t * sol / (v + sol)
            if dt < float(r.tok) / (1.0 + PA.slack_of(r.sh)): continue
            if cut > 0 and rng.random() < cut: continue
            v += sol; t -= dt
        else:
            tk = float(r.tok); so = v * tk / (t + tk); v -= so; t += tk
        frs = r.fr
        if v >= PA.GRADV: break
    return v * q / (t + q) * (1.0 - frs) / 1e9 - size


def simulate(Wd, rule, rep, t2_on=True, verbose=False):
    tape, A, R, cal = Wd.tape, Wd.A, Wd.R, Wd.cal
    iv = cal["iv"]
    heap = []; seq = [0]
    def push(t, typ, a=None, b=None):
        seq[0] += 1; heapq.heappush(heap, (t, seq[0], typ, a, b))
    wins = []
    armed = {}; recount = collections.Counter(); pos_open = collections.Counter(); free_at = {}; ata_until = {}; inflight = {}; pos_close = {}
    t2_arm_times = collections.defaultdict(list)
    npos = [0]; positions = []
    caps = Caps()
    fees = deque(); fee_sum = [0]; fee_pause = [0.0]
    stats = collections.Counter()
    skips = collections.Counter()
    cands, tape_skips = Wd.candidates(rule) if rule is not None else ([], collections.Counter())
    for k, v in tape_skips.items(): skips[k] += v
    if t2_on:
        for P in Wd.t2:
            if Wd.t_start <= P.t_trig <= Wd.t_end: push(P.t_trig, "T2", P)
    for cd in cands: push(cd["t_chk"], "CHK", cd)
    Ls = R.L; nL = len(Ls); Ds = R.D; nD = len(Ds)

    def block_until(m, t):
        b = 0.0
        if pos_open[m] > 0: b = max(b, pos_close.get(m, t) + MARGIN)
        b = max(b, free_at.get(m, 0.0), ata_until.get(m, 0.0), inflight.get(m, 0.0))
        return b

    def stop(w, t, why):
        if w.stopped: return
        w.stopped = True; w.end_t = t; w.end_why = why
        if armed.get(w.mint) == w.wid: armed.pop(w.mint, None)
        if w.last_dl is not None:
            inflight[w.mint] = max(inflight.get(w.mint, 0.0), (w.last_dl + 1) * SMS + w.P.off_s)

    def new_win(kind, key, mint, P, size, en, t0, t_stop, why_stop, t_arm, cand=None, nth=0):
        w = WinSt()
        w.wid = len(wins); w.key = key; w.kind = kind; w.mint = mint; w.P = P; w.size = size; w.drop = 0.12; w.en = en; w.t0 = t0; w.t_stop = t_stop
        w.why_stop = why_stop; w.n = 0; w.sent = 0; w.refused = 0; w.paused = 0; w.landed = 0; w.best = None; w.bver = 0; w.stopped = False
        w.end_t = None; w.end_why = None; w.last_dl = None; w.rng = rng_for(rep, Wd.run, key); w.cand = cand; w.nth = nth; w.t_arm = t_arm; w.filled = False; w.res = None
        wins.append(w)
        armed[mint] = w.wid
        push(t0, "TICK", w.wid); push(t_stop, "END", w.wid)
        return w

    def arm_rearm(cd, t, deferred):
        m = cd["mint"]; tl = tape.tok(m)
        if deferred:
            arm_slot = Wd.slot_at(t)
            k_from = Wd.first_seen_ge(tl, t)
        else:
            arm_slot = cd["check_slot"]; k_from = None
        if arm_slot > cd["en_slot"]: skips["rearm_deferred_expired"] += 1; return
        kt = cd["k"] if not cd["chained"] else cd["k_trig"]
        P = Wd.window_P(m, tl, kt, cd["key"], cd["en_slot"], 650_000_000)
        if P is None: skips["rearm_no_tape"] += 1; return
        t_stop, why, _ = M.natural_end(tape, tl, rule, A, t, arm_slot, cd["en_slot"], k_from)
        t_stop += cal["end_dt"].get(why, 0.0)
        recount[m] += 1
        new_win("rearm", cd["key"], m, P, 0.65, cd["en_slot"], t + cal["first_re"], t_stop, why, t, cd, recount[m])
        stats["rearm_windows"] += 1
        if deferred: stats["rearm_armed_after_wait"] += 1
        if cd["chained"]: stats["chained_windows"] += 1

    def chain_after(w, t, sell_slot):
        m = w.mint
        if rule is None or not rule.chain: return
        if w.kind == "t2" and not rule.chain_t2: return
        tl = tape.tok(m)
        if tl.n == 0 or not tl.hist or tl.mayhem: return
        k = Wd.first_seen_ge(tl, t) - 1
        if k < 0 or k >= tl.out_k: return
        if tl.nbig[rule.hold_pct][k] <= 0: stats["chain_no_holder"] += 1; return
        if rule.max_age is not None and sell_slot - tl.s0 > rule.max_age: stats["chain_age"] += 1; return
        cd = {"mint": m, "k": None, "k_trig": k, "check_slot": Wd.slot_at(t), "t_chk": t, "en_slot": sell_slot + M.WAIT + rule.gap, "chained": True,
              "key": (m, "chain", int(tl.s[k]), int(tl.i[k]), w.wid), "n_hold": int(tl.nbig[rule.hold_pct][k]), "age": sell_slot - tl.s0}
        push(t, "CHK", cd)

    while heap:
        t, _, typ, a, b = heapq.heappop(heap)
        if typ == "TICK":
            w = wins[a]
            if w.stopped: continue
            P = w.P
            slot = int((t - P.off_s) // SMS)
            if t >= w.t_stop or slot > w.en: continue          # END handles it
            w.n += 1
            nxt = t + iv
            if npos[0] > 0: w.paused += 1; push(nxt, "TICK", a); continue
            while fees and fees[0][0] < t - 86_400_000.0: fee_sum[0] -= fees.popleft()[1]
            if fee_sum[0] >= BUDGET: fee_pause[0] += iv; push(nxt, "TICK", a); continue
            ri = (w.n + w.wid) % 2
            if not caps.ok(t, ri): w.refused += 1; push(nxt, "TICK", a); continue
            w.sent += 1
            dl = min(slot + 1, w.en)
            w.last_dl = dl if w.last_dl is None else max(w.last_dl, dl)
            rng = w.rng
            if rng.random() < R.p_unseen:
                push(nxt, "TICK", a); continue
            V, T, _ = L.state_at_c(P, t - P.off)
            c = t - P.off + max(5.0, float(Ls[rng.integers(nL)]))
            s, i = P.pos_of(c)
            w.landed += 1
            fees.append((c + P.off, FAIL)); fee_sum[0] += FAIL
            if s <= dl and V < M.UNTRADE_V:
                mo, _ = L.limit_min_out(V, T, int(round(w.size * 1e9)), L.FR, w.drop)
                V2, T2, kn = L.state_before(P, s, i)
                tok, xn = L.buy_out(V2, T2, int(round(w.size * 1e9)))
                ok_g = True
                if GUARD.startswith('dump') and w.kind == 'rearm' and tok >= mo:   # GUARD (STATE's idea): the dumper's remaining bag
                    tl = tape.tok(w.mint)                                    # GUARD
                    kl = int(np.searchsorted(tl.s * 1000000 + tl.i, s * 1000000 + i))   # GUARD
                    gd = tape.gid.get(w.P.whale)                             # GUARD: the dump seller (window trigger wallet)
                    qs = np.nonzero(tl.user[:kl] == gd)[0] if gd is not None else []   # GUARD
                    bl = int(tl.bal_after[qs[-1]]) if len(qs) else 0         # GUARD
                    if bl >= float(GUARD[4:]) / 100 * M.SUPPLY: ok_g = False; stats['guard_blocked'] += 1   # GUARD
                elif GUARD != 'off' and w.kind == 'rearm' and tok >= mo:   # GUARD
                    tl = tape.tok(w.mint)                                    # GUARD
                    kl = int(np.searchsorted(tl.s * 1000000 + tl.i, s * 1000000 + i))   # GUARD: trades strictly before our landing (s, i)
                    ks = Wd.first_seen_ge(tl, t)                             # GUARD: trades seen at signing = [0, ks)
                    if kl > 0 and tl.nbig[6][kl - 1] > 0: ok_g = False       # GUARD: a >= 6% holder still there
                    elif GUARD == 'naive' and kl > ks:                       # GUARD
                        for q in range(max(ks, 0), kl):                      # GUARD
                            if (not tl.buy[q]) and tl.bal_after[q] == 0 and tl.tok[q] >= 0.06 * M.SUPPLY and rng.random() < PCLOSE: ok_g = False; break
                    if not ok_g: stats['guard_blocked'] += 1                 # GUARD
                if ok_g and tok >= mo and V2 < M.UNTRADE_V and (w.best is None or (s, i) < w.best[0]):
                    w.best = ((s, i), c, kn, V2, T2, tok, xn, t)
                    w.bver += 1
                    push(c + P.off, "FILL", a, w.bver)
            push(nxt, "TICK", a)
        elif typ == "END":
            w = wins[a]
            if not w.stopped: stop(w, t, w.why_stop)
        elif typ == "FILL":
            w = wins[a]
            if b != w.bver or w.filled: continue
            w.filled = True
            stop(w, t, "filled")
            P = w.P
            (fs, fi), c, kn, Vb, Tb, tok, xn, tsend = w.best
            rng = w.rng
            Dw = float(Ds[rng.integers(nD)])
            cfg = Wd.cfg_t2 if w.kind == "t2" else Wd.cfg_re
            ex = L.exit_walk(P, kn, Tb, tok, int(round(w.size * 1e9)), t, Dw, R.tau, cfg, R, rng, False, fs)
            t_sell = ex["t_dec"] + Dw
            t_close = t_sell + R.C
            acl = float(Wd.ata_clear[rng.integers(len(Wd.ata_clear))])
            m = w.mint
            if npos[0] > 0: stats["double_position"] += 1
            npos[0] += 1; pos_open[m] += 1; pos_close[m] = max(pos_close.get(m, 0.0), t_close)
            ata_until[m] = max(ata_until.get(m, 0.0), t_sell + acl)
            positions.append((t, t_close, w.wid))
            sell_slot = int(ex["c_sell"] // SMS)
            w.res = {"fs": fs, "fi": fi, "t_fill": t, "t_close": t_close, "c_sell": ex["c_sell"], "gross": ex["gross"], "why": ex["why"], "p_entry": (Vb + xn) / (Tb - tok),
                     "sell_slot": sell_slot}
            push(t_close, "CLOSE", a, sell_slot)
        elif typ == "CLOSE":
            w = wins[a]; m = w.mint
            npos[0] -= 1; pos_open[m] -= 1
            free_at[m] = max(free_at.get(m, 0.0), t + MARGIN)
            chain_after(w, t, b)
        elif typ == "T2":
            P = a; m = P.mint
            if pos_open[m] > 0 or t < free_at.get(m, 0.0): skips["t2_blocked_position"] += 1; continue
            if t < ata_until.get(m, 0.0): skips["t2_blocked_ata_open"] += 1; continue
            cur = armed.get(m)
            if cur is not None:
                if wins[cur].kind == "t2": skips["t2_blocked_armed"] += 1; continue
                stop(wins[cur], t, "superseded")
            t2_arm_times[m].append(t)
            t_stop, en = L.stop_times(P, Wd.cfg_t2, R)
            new_win("t2", ("t2", P.W["w"]), m, P, Wd.cfg_t2["size"], en, t + cal["first_t2"], t_stop, "t2_stop", t)
            stats["t2_windows"] += 1
        elif typ == "CHK":
            cd = a; m = cd["mint"]
            cur = armed.get(m)
            if cur is not None: skips["rearm_blocked_live_armed" if wins[cur].kind == "t2" else "rearm_blocked_rearm_armed"] += 1; continue
            if Wd.launch_refusal(m): skips["rearm_blocked_launch"] += 1; continue
            if rule.cap is not None and recount[m] >= rule.cap: skips["rearm_cap"] += 1; continue
            bu = block_until(m, t)
            if bu > t:
                stats["rearm_deferred"] += 1
                push(bu, "WAKE", cd, t)
                continue
            arm_rearm(cd, t, False)
        elif typ == "WAKE":
            cd = a; t_chk = b; m = cd["mint"]
            if any(t_chk < x <= t for x in t2_arm_times.get(m, ())): skips["rearm_blocked_superseded_wait"] += 1; continue
            cur = armed.get(m)
            if cur is not None: skips["rearm_blocked_armed_wait"] += 1; continue
            tl = tape.tok(m)
            st = M.stops_while_waiting(tape, tl, rule, A, t_chk, t, cd["check_slot"]) if not cd["chained"] else \
                M.stops_while_waiting(tape, tl, rule, A, t_chk, t, Wd.slot_at(t_chk) - 1)
            if st: skips["rearm_wait_" + st[1]] += 1; continue
            if Wd.slot_at(t) > cd["en_slot"]: skips["rearm_wait_expired"] += 1; continue
            if rule.cap is not None and recount[m] >= rule.cap: skips["rearm_cap"] += 1; continue
            bu = block_until(m, t)
            if bu > t + 1e-6: push(bu, "WAKE", cd, t_chk); continue
            arm_rearm(cd, t, True)
    # results per window
    out = []
    for w in wins:
        fails = w.landed - (1 if w.filled else 0)
        r = {"wid": w.wid, "key": w.key, "kind": w.kind, "mint": w.mint, "t_arm": w.t_arm, "end_why": w.end_why, "ticks": w.n, "sent": w.sent, "refused": w.refused,
             "paused": w.paused, "fails": fails, "filled": w.filled, "nth": w.nth, "chained": bool(w.cand and w.cand.get("chained")),
             "dump_age": (w.cand or {}).get("age"), "n_hold": (w.cand or {}).get("n_hold")}
        if w.filled:
            x = w.res
            r.update({k: x[k] for k in ("fs", "fi", "t_fill", "t_close", "c_sell", "why", "p_entry", "sell_slot")})
            r["gross_naive"] = x["gross"] / 1e9 - w.size
            recs = Wd.recs(w.mint)
            mi = PA.last_before(recs, (x["fs"], x["fi"], -1)) if recs else None
            if mi is not None:
                vn = PA.value_at(recs, mi, w.size, False, x["c_sell"], tape.maxi, by_cc=True)
                vs = PA.value_at(recs, mi, w.size, True, x["c_sell"], tape.maxi, by_cc=True)
                vc = value_cut(recs, mi, w.size, x["c_sell"], tape.maxi, 0.2, rng_for(rep, "cut", Wd.run, w.key))
                if vn and vs and vc is not None:
                    r["d_slip"] = vs["gross"] - vn["gross"]; r["d_cut"] = vc - vn["gross"]
                    r["followers"] = vs["followers"]; r["dropped"] = vs["dropped"]
            r.setdefault("d_slip", 0.0); r.setdefault("d_cut", 0.0)
            r["cash_naive"] = r["gross_naive"] - FIX / 1e9 - fails * FAIL / 1e9
        else:
            r["cash_naive"] = -fails * FAIL / 1e9; r["d_slip"] = 0.0; r["d_cut"] = 0.0
        r["cash"] = r["cash_naive"] + r["d_slip"]
        r["cash_cut"] = r["cash_naive"] + r["d_cut"]
        out.append(r)
    meta = {"stats": dict(stats), "skips": dict(skips), "fee_pause_ms": fee_pause[0], "fees_total": fee_sum[0] / 1e9, "n_cands": len(cands),
            "hours": (Wd.t_end - Wd.t_start) / 3.6e6, "t_start": Wd.t_start, "t_end": Wd.t_end}
    return out, meta


def rule_from(d):
    if d is None: return None
    return M.Rule(**d)


if __name__ == "__main__":
    ctxp, rj, rep, outp = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
    Wd = World(ctxp)
    d = json.loads(rj)
    rule = rule_from(d)
    res, meta = simulate(Wd, rule, rep, t2_on=True)
    pickle.dump({"rule": d, "rep": rep, "res": res, "meta": meta}, open(outp, "wb"))
    df = collections.Counter(); cash = collections.defaultdict(float)
    for r in res:
        df[r["kind"]] += r["filled"]; cash[r["kind"]] += r["cash"]
    print(d and d.get("name"), "rep", rep, "windows", collections.Counter(r["kind"] for r in res), "fills", dict(df), "cash", {k: round(v, 3) for k, v in cash.items()}, meta["stats"], meta["skips"])
