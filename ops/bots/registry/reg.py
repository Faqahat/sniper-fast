"""BOTREG core: discovery, operator linking, lifecycle and output. Used by update.py (live, incremental) and x4_backtest.py
(hour-by-hour replay). Every decision at update time t uses only hourly counters and fingerprints of hours < t.

STATES  new -> probation -> active -> dormant -> retired   (dormant -> back to its earlier state when it trades again)
ENGINE VIEW = probation + active + dormant (a dormant wallet costs nothing to watch; it comes back without a reload)."""
import json, os, math, time, collections
import numpy as np
import common as C

CFG = {
    "W_DISC_H": 48,            # discovery window, covered hours (recording gaps do not count)
    "W_RECENT_H": 24,
    # loose bar -> state 'new' (tracked for linking, not in the engine view); 24 h window
    "LOOSE": {"n_dip": 10, "trips_pd": 15, "dip_share": 0.20},
    # P1 profitable dip bot (48 h window). Fixed cohort (flatsig f5) used 3.7 DEV days: closed >= 150, net >= 1.5 SOL,
    # mean >= 1 mSOL, dip share >= 0.35  (= about 40 trips/day and +0.4 SOL/day)
    "P1": {"trips_pd": 40, "dip_share": 0.30, "pnl_pd_sol": 0.25, "mean_msol": 0.5, "short_hold": 0.80},
    # P2 follower of our fills (48 h window), P&L not required (our profit comes from them, winners or not)
    "P2": {"fol_fills": 8, "fol_rate": 0.03, "dip_share": 0.25, "trips_pd": 20},
    # P3 linked successor: confidence high to a known operator + >= 10 dip buys in 24 h
    "P3": {"n_dip_24h": 10},
    "PROMOTE": {"min_prob_h": 6, "cum_trips": 100, "cum_fol_fills": 20, "linked_cum_trips": 30},
    "DORMANT_H": 6,            # no trade in the last 6 covered hours
    "REVIVE": {"n_dip_6h": 3},
    "RETIRE_DORMANT_H": 72,    # dormant for 72 covered hours
    "PROBATION_MAX_H": 48,     # probation without re-qualifying for 48 covered hours -> retired
    # SELLS INTO US (from our own on-chain positions before t; our P&L = our sell - our buy - 1.25%/side, MEASURED on chain)
    "SELL": {"S1_loss_n": 3, "S1_pnl_sol": -0.03, "S1_loss_share": 0.5, "S1_held_mean_sol": -0.005,   # repeat seller into our hold
             "S2_pos_pnl": -0.01, "S2_pairs": 2, "S2_max_group": 8,              # co-sellers in >= 2 of the same losing holds
             "S3_trig_n": 3, "S3_pnl_sol": -0.03, "S3_mean_sol": -0.005, "S3_loss_share": 0.6,   # trigger dumper of our losers
             # S4 bait: >= 2 outside wallets each buying >= 1% (one >= 5% = whale) within 6 slots before our fill, on a token aged
             # >= 300 slots with <= 3 distinct buyers in the 50 slots before that cluster; >= 2 of them sold into our hold
             "S4_cluster_slots": 6, "S4_min_pct": 1.0, "S4_whale_pct": 5.0, "S4_min_age": 300, "S4_quiet_buyers": 3, "S4_quiet_slots": 50,
             "DORMANT_H": 24, "RETIRE_H": 168},
    "LINK": {"fp_hours": 72, "min_share": 0.05, "rare_df": 8, "min_ntx": 30},
}
# fingerprint families. STRONG = operator-owned accounts/programs. MEDIUM groups count once each; the compute-budget
# group (cup/cupm/cul/fee are one recipe) needs >= 2 rare matching tokens.
STRONG = ("prog", "aux")
GROUPS = {"cup": "cb", "cupm": "cb", "cul": "cb", "fee": "cb", "bsz": "size", "tipa": "tip", "ixs": "ix"}
DAY = 24.0


class Window:
    """per-wallet sums over a set of hours from the hourly table (sorted by h)"""
    COLS = ("n_buy", "buy_sol", "n_sell", "n_dip", "dip_sol", "n_fol", "n_fol_fills", "n_trip", "pnl", "n_win",
            "hold0", "hold1", "hold2", "hold3", "hold4", "hold5", "n_fail", "n_fail_dip")

    def __init__(self, T, hours):
        hs = np.asarray(sorted(hours), np.int64)
        self.nh = len(hs)
        a = np.searchsorted(T["h"], hs); b = np.searchsorted(T["h"], hs, side="right")
        rows = np.concatenate([np.arange(x, y) for x, y in zip(a, b)]) if len(hs) else np.zeros(0, np.int64)
        u = T["u"][rows]
        self.u, inv = np.unique(u, return_inverse=True)
        self.S = {c: np.bincount(inv, weights=T[c][rows].astype(np.float64), minlength=len(self.u)) for c in self.COLS}
        last = np.zeros(len(self.u), np.int64); np.maximum.at(last, inv, T["last_bt"][rows])
        self.S["last_bt"] = last
        G = T["_G"]; gi = np.isin(G["h"], hs)
        self.our_fills = float(G["g_our_fills"][gi].sum())
        self.pos = {int(x): i for i, x in enumerate(self.u)}

    def get(self, u):
        i = self.pos.get(u)
        if i is None: return None
        s = {c: float(v[i]) for c, v in self.S.items()}
        days = max(self.nh, 1) / DAY
        s["trips_pd"] = s["n_trip"] / days; s["pnl_pd_sol"] = s["pnl"] / 1e9 / days
        s["mean_msol"] = s["pnl"] / 1e6 / s["n_trip"] if s["n_trip"] else 0.0
        s["dip_share"] = s["n_dip"] / s["n_buy"] if s["n_buy"] else 0.0
        s["short_hold"] = sum(s[f"hold{k}"] for k in range(5)) / s["n_trip"] if s["n_trip"] else 0.0
        s["fol_rate"] = s["n_fol_fills"] / self.our_fills if self.our_fills else 0.0
        s["fails_pd"] = s["n_fail"] / days
        return s

    def mask(self, cond):
        return [int(x) for x in self.u[cond(self.S, max(self.nh, 1) / DAY)]]


def loose_ok(s):
    L = CFG["LOOSE"]
    return s is not None and s["n_dip"] >= L["n_dip"] and s["trips_pd"] >= L["trips_pd"] and s["dip_share"] >= L["dip_share"]


def p1_ok(s):
    P = CFG["P1"]
    return s is not None and all(s[k] >= v for k, v in P.items())


def p2_ok(s):
    P = CFG["P2"]
    return (s is not None and s["n_fol_fills"] >= P["fol_fills"] and s["fol_rate"] >= P["fol_rate"]
            and s["dip_share"] >= P["dip_share"] and s["trips_pd"] >= P["trips_pd"])


# ---------------------------------------------------------------- fingerprints / linking
class FPStore:
    """fingerprint counters per wallet over a sliding window of the last fp_hours (hours must be added in time order).
    A wallet that leaves the window keeps a frozen copy of its last window (so retired wallets can still be linked to)."""

    def __init__(self):
        self.b58 = {}
        self.q = collections.deque()                   # [(hour, recs)]
        self.win = {}                                  # u -> [ntx, Counter]
        self.frozen = {}
        self.dirty = set()
        self._sh = {}
        self.t = None

    def add_hour(self, h, recs):
        for u, r in recs.items():
            self.b58.setdefault(u, r["b58"])
            w = self.win.get(u)
            if w is None: w = self.win[u] = [0, collections.Counter()]
            w[0] += r["ntx"]; w[1].update(r["tok"]); self.dirty.add(u)
        self.q.append((h, recs))
        while self.q and self.q[0][0] < h + C.H - CFG["LINK"]["fp_hours"] * C.H:
            _, old = self.q.popleft()
            for u, r in old.items():
                w = self.win[u]
                if w[0] - r["ntx"] <= 0:
                    self.frozen[u] = w; del self.win[u]
                else:
                    w[0] -= r["ntx"]; w[1].subtract(r["tok"]); w[1] = +w[1]; self.dirty.add(u)
        self.t = h + C.H
        self.clean()

    def backfill(self, h, recs):
        """add fingerprints of wallets that joined the watch set later, for an hour already inside the window"""
        for qh, qr in self.q:
            if qh == h:
                for u, r in recs.items():
                    if u in qr: continue
                    qr[u] = r; self.b58.setdefault(u, r["b58"])
                    w = self.win.get(u)
                    if w is None: w = self.win[u] = [0, collections.Counter()]
                    w[0] += r["ntx"]; w[1].update(r["tok"]); self._sh.pop(u, None)
                return

    def population(self, t):
        return set(self.win)

    def profile(self, u, t=None):
        w = self.win.get(u) or self.frozen.get(u)
        return (w[0], w[1]) if w else None

    def shares_at(self, u, t=None):
        if u in self._sh: return self._sh[u]
        pr = self.profile(u)
        r = shares(pr) if pr and pr[0] >= CFG["LINK"]["min_ntx"] else None
        self._sh[u] = r
        return r

    def clean(self):
        for u in self.dirty: self._sh.pop(u, None)
        self.dirty = set()


def shares(prof):
    n, c = prof
    ms = CFG["LINK"]["min_share"]
    return {k: v / n for k, v in c.items() if v > 0 and v / n >= ms and not k.startswith(("err:", "nsig:", "tip:"))}, \
           {k: v / n for k, v in c.items() if k.startswith("tip:") and v / n >= ms}


def link_scan(cands, refs, fp, t, first_seen, last_seen, stats_of, data_start):
    """cands: wallets to link; refs: {u: op} known wallets. Rarity (df) is measured over every fingerprinted wallet active
    in the last 72 h (the whole watch population), so shared services / terminals / tip lanes do not count as operator marks.
    A token is RARE for operator O if df <= rare_df, or >= 80% of the wallets carrying it already belong to O.
    Returns {u: best link dict or None}."""
    L = CFG["LINK"]
    pop = fp.population(t) | set(cands) | set(refs)
    P = {}
    for u in pop:
        sh = fp.shares_at(u, t)
        if sh: P[u] = sh
    if not P: return {}
    carriers = collections.defaultdict(set)
    for u, (sh, _) in P.items():
        for k in sh:
            if k.split(":")[0] in STRONG or k.split(":")[0] in GROUPS: carriers[k].add(u)
    opw = collections.defaultdict(set)
    for u, op in refs.items(): opw[op].add(u)
    def rare(k, op):
        c = carriers[k]
        return len(c) <= L["rare_df"] or len(c & opw[op]) >= 0.8 * len(c)
    inv = collections.defaultdict(set)
    for u in refs:
        if u in P:
            for k in P[u][0]:
                if k in carriers: inv[k].add(u)
    pref = collections.defaultdict(set)
    for u in refs:
        b = fp.b58.get(u)
        if b: pref[b[:4]].add(u)
    def handoff(x, y):
        fx, ly = first_seen.get(x), last_seen.get(y)
        return (fx and ly and fx >= data_start + 6 * C.H and fx - 48 * C.H <= ly <= fx + C.H and t >= ly + 2 * C.H
                and first_seen.get(y, fx) < fx)
    out = {}
    for x in cands:
        if x not in P: out[x] = None; continue
        shx, tipx = P[x]
        bx = fp.b58.get(x, "")
        ys = set()
        for k in shx:
            if k in inv and len(carriers[k]) <= 60: ys |= inv[k]
        ys |= pref.get(bx[:4], set())
        ys |= {y for y in refs if handoff(x, y)}
        ys.discard(x)
        best = None
        for y in ys:
            if y not in P: continue
            op = refs[y]
            shy, tipy = P[y]
            ev = []; ns = 0; grp = collections.Counter()
            for k in shx.keys() & shy.keys():
                fam = k.split(":")[0]
                if fam not in STRONG and fam not in GROUPS: continue
                if not rare(k, op): continue
                if fam in STRONG and min(shx[k], shy[k]) >= 0.10: ns += 1
                elif fam in GROUPS: grp[GROUPS[fam]] += 1
                else: continue
                ev.append(f"{k[:56]} (carried by {len(carriers[k])} wallets, {shx[k]:.0%}/{shy[k]:.0%} of txs)")
            nm = sum(1 for g, n in grp.items() if n >= (2 if g == "cb" else 1))
            nw = 0
            by = fp.b58.get(y, "")
            if bx[:4] and bx[:4] == by[:4]: nw += 1; ev.append(f"vanity prefix '{bx[:4]}' (weak: cheap to grind)")
            if handoff(x, y):
                nw += 1; ev.append(f"hand-off: old wallet's last trade {C.pkt(last_seen[y])}, new wallet's first {C.pkt(first_seen[x])}")
            if tipx and tipy:
                j = len(tipx.keys() & tipy.keys()) / len(tipx.keys() | tipy.keys())
                if j >= 0.5: nw += 1; ev.append(f"same tip accounts (Jaccard {j:.2f}, weak: shared lanes)")
            sx, sy = stats_of(x), stats_of(y)
            if sx and sy and sx["n_trip"] >= 20 and sy["n_trip"] >= 20:
                hx = np.array([sx[f"hold{k}"] for k in range(6)]); hy = np.array([sy[f"hold{k}"] for k in range(6)])
                cos = float(hx @ hy / (np.linalg.norm(hx) * np.linalg.norm(hy) + 1e-9))
                if cos >= 0.97 and abs(sx["dip_share"] - sy["dip_share"]) <= 0.1:
                    nw += 1; ev.append(f"same behaviour (hold-profile cos {cos:.2f}, dip share {sx['dip_share']:.2f}/{sy['dip_share']:.2f})")
            if ns >= 2 or (ns >= 1 and nm >= 1): conf = "high"
            elif ns >= 1 or nm >= 3 or (nm >= 2 and nw >= 2): conf = "medium"
            elif nm >= 1 and nw >= 1: conf = "low"
            else: continue
            score = 3 * ns + 1.5 * nm + 0.5 * nw
            if best is None or score > best["score"]:
                best = {"to": y, "op": op, "confidence": conf, "score": score, "evidence": ev,
                        "strong": ns, "medium_groups": nm, "weak": nw}
        out[x] = best
    return out


# ---------------------------------------------------------------- registry
def bait_event(p):
    """S4 pattern on one of our positions (chain data up to our hold only). Returns (cluster wallets, whale) or None."""
    X = CFG["SELL"]
    if p.get("pre") is None or p["age"] < X["S4_min_age"] and not p.get("age_cens"): return None
    s0 = p["slot"] - X["S4_cluster_slots"]
    buys = collections.defaultdict(float); first = {}
    for u, b, pct, sol, sl in p["pre"]:
        if b == 1 and sl >= s0:
            buys[u] += pct; first[u] = min(first.get(u, sl), sl)
    cl = {u: v for u, v in buys.items() if v >= X["S4_min_pct"]}
    if len(cl) < 2: return None
    wh = max(cl, key=cl.get)
    if cl[wh] < X["S4_whale_pct"]: return None
    c0 = min(first[u] for u in cl)
    if p["slot"] - p["age"] > c0 - X["S4_min_age"] and not p.get("age_cens"): return None    # token too young at the cluster
    quiet = {u for u, b, pct, sol, sl in p["pre"] if b == 1 and c0 - X["S4_quiet_slots"] <= sl < c0}
    if len(quiet) > X["S4_quiet_buyers"]: return None
    sold = {u for u, sol, pct in p["sellers"] if u in cl and sol >= 0.05}
    if len(sold) < 2: return None
    return set(cl), wh


class Registry:
    def __init__(self):
        self.W = {}              # u -> record
        self.ops = {}            # op -> {"label", "wallets"}
        self.version = 0
        self.cum = {}            # u -> Counter of cumulative hourly sums since first seen
        self.first_seen = {}     # u -> first activity time (block time) in the data
        self.last_seen = {}      # u -> last trade time
        self.log = []            # transitions
        self._track = set()
        self.pos = []            # our on-chain positions (x1 *.ours.pkl), time ordered
        self.S = {}              # seller u -> record

    # -- cumulative counters (incremental: add one completed hour at a time)
    def add_hour(self, T, h):
        a = np.searchsorted(T["h"], h); b = np.searchsorted(T["h"], h, side="right")
        for r in range(a, b):
            u = int(T["u"][r])
            if T["n_buy"][r] + T["n_sell"][r] > 0:
                if u not in self.first_seen: self.first_seen[u] = int(T["first_bt"][r])
                self.last_seen[u] = max(self.last_seen.get(u, 0), int(T["last_bt"][r]))
            if u in self.W or u in self._track:
                c = self.cum.setdefault(u, collections.Counter())
                for k in ("n_trip", "pnl", "n_dip", "n_buy", "n_fol_fills"): c[k] += float(T[k][r])

    def _set(self, u, st, t, why):
        r = self.W[u]
        if r["state"] == st: return
        self.log.append({"t": t, "u": u, "from": r["state"], "to": st, "why": why})
        r["hist"].append([t, st, why]); r["state"] = st; r["state_since"] = t

    def _new_op(self, u, fp):
        b = fp.b58.get(u, str(u))
        lab = C.SEED_NAMES.get(b)
        op = f"op-{b[:8]}"
        self.ops[op] = {"label": lab or "", "wallets": [u], "created": None}
        return op

    def _join(self, u, op):
        o = self.W[u].get("op")
        if o == op: return
        if o and o in self.ops and u in self.ops[o]["wallets"]:
            self.ops[o]["wallets"].remove(u)
        self.W[u]["op"] = op; self.ops[op]["wallets"].append(u)

    def update(self, T, t, cov, fp, recompute_cov_index=None):
        """one registry update at time t (all hours < t complete). cov = sorted covered hours."""
        hs = [h for h in cov if h < t]
        if not hs: return
        wd = Window(T, hs[-CFG["W_DISC_H"]:]); wr = Window(T, hs[-CFG["W_RECENT_H"]:])
        w6 = Window(T, hs[-CFG["DORMANT_H"]:])
        h_dorm = hs[-CFG["DORMANT_H"]] if len(hs) >= CFG["DORMANT_H"] else hs[0]
        ours = set(C.OURS64)
        # --- discovery
        L = CFG["LOOSE"]
        loose = set(wr.mask(lambda S, d: (S["n_dip"] >= L["n_dip"]) & (S["n_trip"] / d >= L["trips_pd"])
                            & (S["n_dip"] >= L["dip_share"] * np.maximum(S["n_buy"], 1)))) - ours
        p1 = {u for u in loose if p1_ok(wd.get(u))}
        p2 = {u for u in set(wd.mask(lambda S, d: S["n_fol_fills"] >= CFG["P2"]["fol_fills"])) - ours if p2_ok(wd.get(u))}
        for u in loose | p2:
            if u in self.W and self.W[u]["state"] == "retired" and self.W[u]["prob_since"] is None:
                self._set(u, "new", t, "loose bar again")
            if u not in self.W:
                self.W[u] = {"state": "new", "state_since": t, "hist": [[t, "new", "loose bar"]], "op": None, "link": None,
                             "role": None, "qual_last": None, "prob_since": None, "active_since": None, "prev": None}
                self._track.add(u)
                self.cum[u] = collections.Counter()
                # back-fill cumulative counters from first appearance (hourly table rows < t)
                m = (T["u"] == np.uint64(u)) & (T["h"] < t)
                for k in ("n_trip", "pnl", "n_dip", "n_buy", "n_fol_fills"): self.cum[u][k] = float(T[k][m].sum())
        # --- linking for new / probation wallets without a confident link
        refs = {u: r["op"] for u, r in self.W.items() if r["op"] and r["state"] in ("probation", "active", "dormant", "retired")}
        cands = [u for u, r in self.W.items() if r["state"] in ("new", "probation")
                 and (r["link"] is None or r["link"]["confidence"] != "high")]
        links = link_scan(cands, refs, fp, t, self.first_seen, self.last_seen, lambda u: wd.get(u), cov[0]) if cands and refs else {}
        for u, lk in links.items():
            if lk and (self.W[u]["link"] is None or lk["score"] > self.W[u]["link"]["score"]):
                lk = dict(lk); lk["t"] = t; self.W[u]["link"] = lk
                if lk["confidence"] == "high" and not self.W[u].get("link_high_t"): self.W[u]["link_high_t"] = t
                o = self.W[u]["op"]
                if (lk["confidence"] == "high" and o and o != lk["op"] and lk["op"] in self.ops
                        and self.ops.get(o, {}).get("wallets") == [u]):      # singleton operator -> merge into the linked one
                    self._join(u, lk["op"]); self.ops.pop(o, None)
        # --- transitions
        for u, r in self.W.items():
            st = r["state"]; sd = wd.get(u); sr = wr.get(u)
            lk = r["link"]
            q1, q2 = u in p1, u in p2
            q3 = (lk is not None and lk["confidence"] == "high" and sr is not None and sr["n_dip"] >= CFG["P3"]["n_dip_24h"]
                  and st in ("new",))
            qual = q1 or q2 or q3
            if qual: r["qual_last"] = t
            last = self.last_seen.get(u, 0)
            if st == "new":
                if qual:
                    r["role"] = "dipbot" if q1 else ("follower" if q2 else "linked")
                    r["prob_since"] = t
                    self._set(u, "probation", t, "P1 profitable dip bot" if q1 else ("P2 follows our fills" if q2 else
                              f"P3 linked to {lk['op']} ({lk['confidence']})"))
                    # operator id
                    if lk and lk["confidence"] == "high" and lk["op"] in self.ops: self._join(u, lk["op"])
                    else:
                        op = self._new_op(u, fp); self.W[u]["op"] = op
                elif sr is None and wd.get(u) is None:
                    self._set(u, "retired", t, "candidate went quiet")
                continue
            if st in ("probation", "active") and last < h_dorm:
                r["prev"] = st; self._set(u, "dormant", t, f"no trade in {CFG['DORMANT_H']} covered h"); continue
            if st == "dormant":
                s6 = w6.get(u)
                if s6 and s6["n_dip"] >= CFG["REVIVE"]["n_dip_6h"] and last >= hs[-1]:
                    self._set(u, r["prev"] or "probation", t, "trading again"); continue
                nd = sum(1 for h in hs if h >= r["state_since"])
                if nd >= CFG["RETIRE_DORMANT_H"]: self._set(u, "retired", t, f"dormant {CFG['RETIRE_DORMANT_H']} covered h")
                continue
            if st == "probation":
                c = self.cum.get(u, {})
                nprob = sum(1 for h in hs if h >= r["prob_since"])
                P = CFG["PROMOTE"]
                ok_recent = loose_ok(sr)
                if r["role"] == "linked" and lk and lk["op"] in self.ops and any(
                        self.W[v]["state"] in ("active", "dormant") or self.W[v].get("active_since") for v in self.ops[lk["op"]]["wallets"] if v != u):
                    promote = c.get("n_trip", 0) >= P["linked_cum_trips"] and c.get("pnl", 0) >= 0
                else:
                    promote = (nprob >= P["min_prob_h"] and ok_recent and
                               ((c.get("n_trip", 0) >= P["cum_trips"] and c.get("pnl", 0) > 0) or c.get("n_fol_fills", 0) >= P["cum_fol_fills"]))
                if promote:
                    r["active_since"] = t; self._set(u, "active", t, "promoted"); continue
                nq = sum(1 for h in hs if h >= (r["qual_last"] or r["prob_since"]))
                if nq >= CFG["PROBATION_MAX_H"]: self._set(u, "retired", t, f"did not re-qualify in {CFG['PROBATION_MAX_H']} covered h")
                continue
            if st == "active":
                if sd is not None and sd["n_trip"] > 0 and not loose_ok(sd) and not q2:
                    r["prob_since"] = t; r["qual_last"] = t; self._set(u, "probation", t, "48 h stats below the loose bar")
                continue
            if st == "retired" and (q1 or q2):
                r["prob_since"] = t; self._set(u, "probation", t, "re-qualified")
        self.version += 1
        self.t = t; self._wd = wd

    # ---------------------------------------------------------------- SELLS INTO US
    def add_positions(self, P):
        self.pos.extend(P)

    def update_sellers(self, t, hs, fp):
        """causal: only our positions with block time < t; flags are recomputed at every update (a wallet that stops
        qualifying is 'cleared'). Registry dip bots are never sellers (they get the 'rival dip bot' tag instead)."""
        X = CFG["SELL"]
        into = collections.defaultdict(lambda: [0, 0, 0.0, 0.0])        # n, n_loss, our pnl sum, sol sold
        trig = collections.defaultdict(lambda: [0, 0, 0.0])             # n, n_loss, our pnl sum
        held = collections.defaultdict(lambda: [0, 0.0])                # our positions where it held >= 0.5% at our fill
        pair = collections.Counter(); pair_pos = collections.defaultdict(list)
        hold_pct = collections.defaultdict(list)
        botset = {u for u, r in self.W.items() if r["state"] in ("probation", "active", "dormant")}
        bait = []                                                        # (position, cluster wallets, whale)
        for p in self.pos:
            if p["bt"] >= t: break
            us = {}
            for u, sol, pct in p["sellers"]:
                if sol < 0.05: continue
                us[u] = us.get(u, 0) + sol
            for u, sol in us.items():
                r = into[u]; r[0] += 1; r[1] += p["pnl"] < 0; r[2] += p["pnl"]; r[3] += sol
            hp = dict(p["holders"])
            for u in us:
                if u in hp: hold_pct[u].append(hp[u])
            for u in hp:
                r = held[u]; r[0] += 1; r[1] += p["pnl"]
            if p["pnl"] <= X["S2_pos_pnl"]:
                ks = sorted(us)
                for i in range(len(ks)):
                    for j in range(i + 1, len(ks)):
                        pair[(ks[i], ks[j])] += 1; pair_pos[(ks[i], ks[j])].append(p)
            if p["trig"]:
                r = trig[p["trig"][0]]; r[0] += 1; r[1] += p["pnl"] < 0; r[2] += p["pnl"]
            ev = bait_event(p)
            if ev: bait.append((p, ev[0], ev[1]))
        self._held = dict(held); self._bait = bait
        flag = {}
        def add(u, rule, ev):
            if u in C.OURS64: return
            hn, hpn = held.get(u, (0, 0.0))
            if hn >= 3 and hpn / hn > X["S1_held_mean_sol"]: return      # we make money when it holds at our fill (rival dip bot)
            if u in flag: flag[u] = (flag[u][0] + "+" + rule, flag[u][1] + "; " + ev)
            else: flag[u] = (rule, ev)
        for u, (n, nl, pn, sol) in into.items():
            hn, hpn = held.get(u, (0, 0.0))
            if hn >= 3 and hpn / hn > X["S1_held_mean_sol"]: continue
            if nl >= X["S1_loss_n"] and pn <= X["S1_pnl_sol"] and nl / n >= X["S1_loss_share"]:
                add(u, "S1", f"sold into {n} of our holds ({nl} losing), our P&L there {pn:+.3f} SOL, sold {sol:.1f} SOL")
        # S2: pairs that sold together into >= 2 of our losing holds AND in >= half of the holds either sold into
        adj = collections.defaultdict(set)
        for (a, b_), c in pair.items():
            if c >= X["S2_pairs"] and c >= 0.5 * min(into[a][0], into[b_][0]): adj[a].add(b_); adj[b_].add(a)
        seen = set(); gid = {}
        for a0 in list(adj):
            if a0 in seen: continue
            comp = set(); st = [a0]
            while st:
                x = st.pop()
                if x in comp: continue
                comp.add(x); st.extend(adj[x] - comp)
            seen |= comp
            if len(comp) > X["S2_max_group"]: continue                    # not a coordinated group: market-wide sellers
            g = "grp-" + fp.b58.get(min(comp), str(min(comp)))[:8]
            gp = {id(p): p for (x, y), L in pair_pos.items() if x in comp and y in comp and adj[x] and y in adj[x] for p in L}
            trigs = collections.Counter(p["trig"][0] for p in gp.values() if p["trig"])
            members = set(comp) | {u for u, c in trigs.items() if c >= 2}
            pn = sum(p["pnl"] for p in gp.values())
            for u in members:
                pcts = hold_pct.get(u)
                gid[u] = g
                add(u, "S2", f"{'co-seller' if u in comp else 'group trigger dumper'} in {g} ({len(members)} wallets): "
                             f"{len(gp)} shared losing holds, our P&L {pn:+.3f} SOL" + (f"; held {np.median(pcts):.1f}% at our fill" if pcts else ""))
        for u, (n, nl, pn) in trig.items():
            if n >= X["S3_trig_n"] and pn <= X["S3_pnl_sol"] and pn / n <= X["S3_mean_sol"] and nl / n >= X["S3_loss_share"]:
                add(u, "S3", f"its dump triggered {n} of our positions ({nl} losing), our P&L {pn:+.3f} SOL")
        # S4 bait: whale + helpers bought together on a quiet old token just before our fill, >= 2 of them sold into our hold, we lost
        for p, cl, wh in bait:
            if p["pnl"] >= 0: continue
            g = "bait-" + fp.b58.get(wh, str(wh))[:8]
            for u in cl:
                gid.setdefault(u, g)
                add(u, "S4", f"bait {'whale' if u == wh else 'helper'} on our losing fill {C.pkt(p['bt'])} (our P&L {p['pnl']:+.3f}; "
                             f"{len(cl)} wallets bought within {X['S4_cluster_slots']} slots on a quiet token aged >= {p['age']} slots, then sold into our hold)")
        # lifecycle (flags recomputed each update)
        for u, (rule, ev) in flag.items():
            r = self.S.get(u)
            if r is None: r = self.S[u] = {"state": None, "since": t, "first_flag": t, "hist": []}
            r["rule"] = rule; r["evidence"] = ev; r["group"] = gid.get(u)
            r["stats"] = {"into": into.get(u, [0, 0, 0, 0])[:3], "trig": trig.get(u, [0, 0, 0]), "held": list(held.get(u, [0, 0.0]))}
        for u, r in self.S.items():
            last = self.last_seen.get(u, 0)
            nq = sum(1 for h in hs if h >= last)
            if u not in flag: st, why = "cleared", ("now a registry dip bot" if u in botset else "no longer meets a rule")
            elif nq > X["RETIRE_H"]: st, why = "retired", "no trade 168 covered h"
            elif nq > X["DORMANT_H"]: st, why = "dormant", "no trade 24 covered h"
            else: st, why = "active", r["rule"]
            if st != r["state"]:
                r["hist"].append([t, st, why]); r["state"] = st; r["since"] = t

    def seller_view(self):
        return {u: r["state"] for u, r in self.S.items() if r["state"] in ("active", "dormant")}

    # ---------------------------------------------------------------- output
    def engine_states(self):
        return {u: r["state"] for u, r in self.W.items() if r["state"] in ("probation", "active", "dormant")}

    def resolve_names(self, fp, max_files=600):
        """fill base58 names for listed wallets/sellers that the fingerprint watch set never saw"""
        need = [u for u in list(self.S) + [u for u, r in self.W.items() if r["state"] != "new" or r["link"]] if u not in fp.b58]
        if need:
            for u, b in C.resolve_b58(need, max_files).items(): fp.b58[u] = b

    def to_json(self, fp, t_data):
        wd = self._wd
        ops = {}
        for op, o in self.ops.items():
            lab = o["label"] or next((C.SEED_NAMES[fp.b58[v]] for v in o["wallets"] if fp.b58.get(v) in C.SEED_NAMES), "")
            ops[op] = {"label": lab, "wallets": [fp.b58.get(v, str(v)) for v in o["wallets"]],
                       "states": [self.W[v]["state"] for v in o["wallets"]]}
        rows = []
        for u, r in self.W.items():
            if r["state"] == "new" and not r["link"]: continue
            s = wd.get(u) or {}
            c = self.cum.get(u, {})
            rows.append({
                "wallet": fp.b58.get(u, str(u)), "u64": str(u), "operator": r["op"], "operator_label": ops.get(r["op"], {}).get("label", ""),
                "state": r["state"], "role": r["role"], "state_since_pkt": C.pkt(r["state_since"]),
                "first_seen_pkt": C.pkt(self.first_seen[u]) if u in self.first_seen else None,
                "last_seen_pkt": C.pkt(self.last_seen[u]) if u in self.last_seen else None,
                "w48": {"trips_per_day": round(s.get("trips_pd", 0), 1), "pnl_sol_per_day": round(s.get("pnl_pd_sol", 0), 3),
                        "mean_msol_per_trip": round(s.get("mean_msol", 0), 2), "dip_share": round(s.get("dip_share", 0), 3),
                        "short_hold_share": round(s.get("short_hold", 0), 3), "failed_buys_per_day": round(s.get("fails_pd", 0), 1),
                        "follow_rate_after_our_fills": round(s.get("fol_rate", 0), 4), "our_fills_followed": int(s.get("n_fol_fills", 0))},
                "rival_tag": ("rival dip bot (holds at our landing)" if getattr(self, "_held", {}).get(u, [0])[0] >= 3 else None),
                "our_pnl_when_it_held_at_fill": ({"n": self._held[u][0], "our_pnl_sol": round(self._held[u][1], 4)} if u in getattr(self, "_held", {}) else None),
                "cum": {"trips": int(c.get("n_trip", 0)), "pnl_sol": round(c.get("pnl", 0) / 1e9, 3), "our_fills_followed": int(c.get("n_fol_fills", 0))},
                "link": ({k: v for k, v in r["link"].items() if k != "to"} | {"to_wallet": fp.b58.get(r["link"]["to"], "")}
                         | {"t_pkt": C.pkt(r["link"]["t"])}) if r["link"] else None,
                "history": [[C.pkt(a), b, c_] for a, b, c_ in r["hist"]],
                "first_seen_epoch": self.first_seen.get(u), "link_high_epoch": r.get("link_high_t"),
                "engine_since_epoch": next((a for a, b, _ in r["hist"] if b == "probation"), None),
            })
        rows.sort(key=lambda x: ({"active": 0, "probation": 1, "dormant": 2, "new": 3, "retired": 4}[x["state"]], -x["w48"]["pnl_sol_per_day"]))
        sellers = []
        for u, r in self.S.items():
            if r["state"] == "cleared" and not r.get("rule"): continue
            sellers.append({"wallet": fp.b58.get(u, str(u)), "u64": str(u), "class": "sells_into_us", "state": r["state"],
                            "rule": r["rule"], "group": r["group"], "evidence": r["evidence"],
                            "our_holds_sold_into": {"n": r["stats"]["into"][0], "losing": r["stats"]["into"][1], "our_pnl_sol": round(r["stats"]["into"][2], 4)},
                            "our_positions_triggered": {"n": r["stats"]["trig"][0], "losing": r["stats"]["trig"][1], "our_pnl_sol": round(r["stats"]["trig"][2], 4)},
                            "our_pnl_when_it_held_at_fill": {"n": r["stats"]["held"][0], "our_pnl_sol": round(r["stats"]["held"][1], 4)},
                            "also_registry_dip_bot": self.W.get(u, {}).get("state") in ("probation", "active", "dormant"),
                            "first_flag_pkt": C.pkt(r["first_flag"]), "last_seen_pkt": C.pkt(self.last_seen[u]) if u in self.last_seen else None,
                            "history": [[C.pkt(a), b, c_] for a, b, c_ in r["hist"]]})
        sellers.sort(key=lambda x: (x["state"] != "active", x["our_holds_sold_into"]["our_pnl_sol"]))
        return {"version": self.version, "generated_pkt": C.pkt(time.time()), "data_through_pkt": C.pkt(t_data),
                "data_through_epoch": int(t_data), "config": CFG,
                "money_note": "P&L = closed bonding-curve trips, sells - buys - 1.25%/side pump fee; network fees/tips not in (MEASURED from recordings)",
                "operators": ops, "wallets": rows, "sellers": sellers}

    def engine_view(self, fp, t_data, stale_s=3 * 3600):
        es = self.engine_states()
        ws = [{"w": fp.b58.get(u, str(u)), "u64": str(u), "state": s, "op": self.W[u]["op"], "role": self.W[u]["role"]}
              for u, s in sorted(es.items(), key=lambda x: x[1])]
        return {"version": self.version, "data_through_epoch": int(t_data), "data_through_pkt": C.pkt(t_data),
                "stale_after_epoch": int(t_data + stale_s), "n": len(ws), "wallets": ws,
                "sellers": [{"w": fp.b58.get(u, str(u)), "u64": str(u), "state": st, "group": self.S[u]["group"], "rule": self.S[u]["rule"]}
                            for u, st in sorted(self.seller_view().items(), key=lambda x: x[1])]}


def write_atomic(path, obj, text=False):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        if text: f.write(obj)
        else: json.dump(obj, f, indent=1)
    os.replace(tmp, path)
