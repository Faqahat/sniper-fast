"""MULTIARM library: the recorder tape of a run as the live detector sees it (tokens followed from their create, balances from
trades, our own trades out), the run's clock anchors, and a Python port of the dip26 re-arm rule (src/bin/snipe_engine/psrearm.rs,
src/presend_live.rs Detector) with the knobs of the multi-arm variants:
  trig_pct / trig_sol   the candidate sell: a single sell >= trig_pct % of supply (or >= trig_sol SOL); the same size of sell also
                        STOPS an armed window ("whale_dump", 30 ms later)
  hold_pct              the holders check (a wallet but ours still holding >= hold_pct %) and the "no_holder" stop
  max_age               the age gate (slots since the create at the dump; None = no gate)
  gap                   the window's last slot = dump slot + 3 + gap
  quiet                 QUIET N:M from the arm (6:2)
Clocks: the block-position clock cc(slot, idx) = slot x 212 + (idx + 0.5) / (max idx + 1) x 212 ms (custom37 / c37lib), and the
feed clock (ms) = cc + A(slot), A = the median feed-arrival offset of nearby chain trades the engine saw (MEASURED from the run's
records); our tries' landing anchor B(slot) = the median (first_rx - cc(landing)) of nearby landed tries."""
import json, math, bisect, collections
import numpy as np

SMS = 212.0
SUPPLY = 1e15
OURS = ("EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE")
UNTRADE_V = 100_000_000_000
STOP_MS = 30.0
WAIT = 3


class Tape:
    """the decoded run tape (pa_decode + real/build.py), indexed by mint"""
    def __init__(self, tab):
        self.tab = tab
        T = np.load(f"{tab}/trades.npy")
        self.T = T
        self.ids = json.load(open(f"{tab}/ids.json"))
        self.gid = {k: i for i, k in enumerate(self.ids)}
        S = np.load(f"{tab}/slots.npy")
        self.slots = S["slot"].astype(np.int64)
        self.maxi_arr = S["maxi"].astype(np.int64)
        self.maxi = dict(zip(self.slots.tolist(), self.maxi_arr.tolist()))
        self.s_lo, self.s_hi = int(self.slots[0]), int(self.slots[-1])
        # the first trade index of every slot (the slot clock moves at the first executed pump tx of a slot)
        ts = T["slot"].astype(np.int64)
        first = np.ones(len(ts), bool); first[1:] = ts[1:] != ts[:-1]
        self.minidx = dict(zip(ts[first].tolist(), T["idx"][first].astype(np.int64).tolist()))
        self.creates = json.load(open(f"{tab}/creates.json"))
        mm = T["mint"]
        self.order = np.argsort(mm, kind="stable")
        self.ms = mm[self.order]
        self.ours = {self.gid[w] for w in OURS if w in self.gid}
        self._tok = {}

    def cc(self, s, i): return s * SMS + (i + 0.5) / (self.maxi.get(s, 400) + 1.0) * SMS

    def slot_ge(self, s):
        """the first slot >= s with a recorded tx (None past the end)"""
        k = int(np.searchsorted(self.slots, s))
        return int(self.slots[k]) if k < len(self.slots) else None

    def slot_start_cc(self, s):
        """block clock of the first trade of slot s (its first recorded tx)"""
        return self.cc(s, self.minidx.get(s, 0))

    def trades(self, mint):
        g = self.gid.get(mint)
        if g is None: return None
        a, b = np.searchsorted(self.ms, g), np.searchsorted(self.ms, g, side="right")
        return self.T[np.sort(self.order[a:b])]

    def tok(self, mint):
        t = self._tok.get(mint)
        if t is None:
            t = TokTL(self, mint)
            self._tok[mint] = t
        return t


class Anchor:
    """a slot -> offset (ms) map from (slot, idx, t_ms) observations: per slot the median offset (t - cc(slot, idx)), linearly
    interpolated between observed slots (the block clock drifts ~2-3 ms per slot against the feed clock: slots are not 212 ms)"""
    def __init__(self, tape, obs):
        per = collections.defaultdict(list)
        for s, i, t in obs:
            if s < tape.s_lo - 50 or s > tape.s_hi + 50: continue
            per[int(s)].append(t - tape.cc(s, i))
        ks = sorted(per)
        self.xs = np.array(ks, dtype=np.float64)
        self.ys = np.array([float(np.median(per[k])) for k in ks])
        self.n = len(ks)
        self.cache = {}

    def __call__(self, s):
        v = self.cache.get(s)
        if v is None:
            v = float(np.interp(s, self.xs, self.ys))
            self.cache[s] = v
        return v


class TokTL:
    """one token as the live detector sees it (presend_live.rs Detector + the observatory Book): followed from its create (not
    mayhem; out from the first of its first 50 trades at curve < 25 / > 200 SOL or vtok 0), balances from trades (ours out of the
    holder counts), counts of non-our wallets holding >= each threshold after every trade"""
    THS = (2, 3, 4, 5, 6, 8)

    def __init__(self, tape, mint):
        self.mint = mint
        t = tape.trades(mint)
        self.n = 0 if t is None else len(t)
        c = tape.creates.get(mint)
        self.create = c
        self.hist = c is not None
        self.s0 = c["slot"] if c else None
        self.mayhem = bool(c and (c.get("mayhem") or c.get("mayhem_ix")))
        if self.n == 0: return
        self.s = t["slot"].astype(np.int64); self.i = t["idx"].astype(np.int64); self.j = t["j"].astype(np.int64)
        self.buy = t["buy"].astype(bool); self.sol = t["sol"].astype(np.int64); self.tok = t["tok"].astype(np.int64)
        self.vsol = t["vsol"].astype(np.int64); self.vtok = t["vtok"].astype(np.int64); self.user = t["user"].astype(np.int64)
        self.fbps = t["fee_bps"].astype(np.int64); self.cbps = t["cfee_bps"].astype(np.int64); self.sh = t["sh"].astype(np.int64)
        self.ours = np.array([u in tape.ours for u in self.user.tolist()], bool)
        self.c = np.array([tape.cc(s, i) for s, i in zip(self.s.tolist(), self.i.tolist())])
        # trades before the create (a reordered delivery) are ignored as the detector does (no token yet)
        n = self.n
        self.out_k = n
        cnt = 0
        for k in range(n):
            if self.hist and self.s[k] < self.s0: continue
            if cnt < 50 and (self.vsol[k] < 25_000_000_000 or self.vsol[k] > 200_000_000_000 or self.vtok[k] == 0):
                self.out_k = k; break
            cnt += 1
        # balances + holder counts after every trade (ours excluded from the counts)
        bal = collections.defaultdict(int)
        nb = {th: 0 for th in self.THS}
        self.nbig = {th: np.zeros(n, np.int32) for th in self.THS}
        self.bal_after = np.zeros(n, np.int64)
        thr = {th: th * SUPPLY / 100 for th in self.THS}
        for k in range(n):
            u = int(self.user[k]); b0 = bal[u]
            b1 = b0 + int(self.tok[k]) if self.buy[k] else b0 - int(self.tok[k])
            bal[u] = b1; self.bal_after[k] = b1
            if not self.ours[k]:
                for th in self.THS:
                    x = thr[th]
                    if b0 < x <= b1: nb[th] += 1
                    elif b1 < x <= b0: nb[th] -= 1
            for th in self.THS: self.nbig[th][k] = nb[th]
        self.key = (self.s * 100000 + self.i).tolist()

    def followed_at(self, k):
        return self.hist and not self.mayhem and k < self.out_k and self.s[k] >= self.s0

    def nbig_before_slot(self, slot, th):
        """non-our wallets >= th % after every trade of a slot < `slot` (the check at the first tx of `slot`)"""
        k = bisect.bisect_left(self.key, slot * 100000) - 1
        return int(self.nbig[th][k]) if k >= 0 else 0

    def holders_before_slot(self, slot, th, tape):
        """[(wallet, pct)] holding >= th % before slot (largest first)"""
        kmax = bisect.bisect_left(self.key, slot * 100000)
        bal = collections.defaultdict(int)
        for k in range(kmax):
            u = int(self.user[k]); bal[u] += int(self.tok[k]) if self.buy[k] else -int(self.tok[k])
        x = th * SUPPLY / 100
        v = [(tape.ids[u], b / SUPPLY * 100) for u, b in bal.items() if b >= x and u not in tape.ours]
        v.sort(key=lambda z: -z[1])
        return v

    def first_k_at_or_after(self, slot):
        return bisect.bisect_left(self.key, slot * 100000)


class Rule:
    """a re-arm rule variant (R0 = the live dip26 rule)"""
    def __init__(self, name, trig_pct=6.0, trig_sol=None, hold_pct=6, max_age=141, gap=20, quiet=(6, 2), cap=None, chain=False, chain_t2=False, min_age=None):
        self.name, self.trig_pct, self.trig_sol, self.hold_pct, self.max_age, self.gap, self.quiet = name, trig_pct, trig_sol, hold_pct, max_age, gap, quiet
        self.min_age = min_age
        self.cap, self.chain, self.chain_t2 = cap, chain, chain_t2
        self.trig_tok = None if trig_pct is None else int(round(trig_pct * SUPPLY / 100))

    def is_big(self, tl, k):
        """the candidate / stop sell"""
        if tl.buy[k]: return False
        if self.trig_sol is not None: return tl.sol[k] >= self.trig_sol * 1e9
        return tl.tok[k] >= self.trig_tok

    def desc(self):
        return {"name": self.name, "trig_pct": self.trig_pct, "trig_sol": self.trig_sol, "hold_pct": self.hold_pct, "max_age": self.max_age, "gap": self.gap,
                "quiet": self.quiet, "cap": self.cap, "chain": self.chain, "chain_t2": self.chain_t2, "min_age": self.min_age}


def candidates(tape, tl, rule, A, s_start):
    """the token's candidate dumps under `rule` (tape only): [(k, check_slot, holders_n, age)] incl. the skips by age / curve"""
    out = []
    if tl.n == 0 or not tl.hist or tl.mayhem or tl.s0 < s_start: return out
    for k in range(tl.n):
        if tl.ours[k] or not tl.followed_at(k) or not rule.is_big(tl, k): continue
        age = int(tl.s[k] - tl.s0)
        if tl.vsol[k] >= UNTRADE_V: out.append({"k": k, "skip": "rearm_untradeable", "age": age}); continue
        if rule.max_age is not None and age > rule.max_age: out.append({"k": k, "skip": "rearm_age", "age": age}); continue
        if rule.min_age is not None and age < rule.min_age: out.append({"k": k, "skip": "rearm_young", "age": age}); continue
        cs = tape.slot_ge(int(tl.s[k]) + WAIT)
        if cs is None: continue
        nh = tl.nbig_before_slot(cs, rule.hold_pct)
        t_chk = tape.slot_start_cc(cs) + A(cs)
        out.append({"k": k, "check_slot": cs, "t_check": t_chk, "n_hold": nh, "age": age, "skip": None if nh > 0 else "rearm_no_holder"})
    return out


def natural_end(tape, tl, rule, A, t_arm, arm_slot, en_slot, k_from=None):
    """the window's own end (feed ms, why) from its arm: the next big sell / no holder (+30 ms), QUIET N:M from the arm slot, its
    last slot passing. k_from = the first token trade after the arm (default: the first trade of slot >= arm_slot)"""
    th = rule.hold_pct
    k0 = tl.first_k_at_or_after(arm_slot) if k_from is None else k_from
    # the first slot >= arm + N and the first slot > en_slot (the slot clock)
    qn, qm = rule.quiet if rule.quiet else (None, None)
    qs = tape.slot_ge(arm_slot + qn) if qn else None
    es = tape.slot_ge(en_slot + 1)
    t_q = tape.slot_start_cc(qs) + A(qs) if qs is not None else math.inf
    t_e = tape.slot_start_cc(es) + A(es) if es is not None else math.inf
    others = 0; decided = qs is None
    for k in range(k0, tl.n):
        s = int(tl.s[k])
        # the slot clock's events before this trade (psrearm.rs rearm_slot: QUIET first, then the last slot)
        if not decided and s >= qs:
            decided = True
            if others < qm and t_q <= t_e: return t_q, "quiet", k
        if es is not None and s >= es: break
        tk = tl.c[k] + A(s)
        if not tl.ours[k]: others += 1
        if rule.is_big(tl, k): return tk + STOP_MS, "whale_dump", k
        if not tl.buy[k] and tl.nbig[th][k] == 0: return tk + STOP_MS, "no_holder", k
    if not decided and others < qm and t_q <= t_e: return t_q, "quiet", None
    return t_e, "expired", None


def stops_while_waiting(tape, tl, rule, A, t_from, t_to, slot_from):
    """a waiting (deferred) window's stops between t_from and t_to: the next big sell / no holder -> (t, why) or None"""
    th = rule.hold_pct
    k0 = tl.first_k_at_or_after(slot_from)
    for k in range(k0, tl.n):
        tk = tl.c[k] + A(int(tl.s[k]))
        if tk < t_from: continue
        if tk >= t_to: break
        if rule.is_big(tl, k): return tk, "whale_dump"
        if not tl.buy[k] and tl.nbig[th][k] == 0: return tk, "no_holder"
    return None
