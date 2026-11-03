"""FILTERS for the joint replay (ma4_sim.simulate(..., flt=Filters(...))): the four prevent-program leads, as the coordinator defined them
(10-30 ~08:10 PKT), each on/off; combinations by name "LW+DLa+BC+STo" etc.
  LW  (STATE's nbuyers50 <= 1, T2 only): a T2 trigger does not arm when the whale is the only buyer (ours excluded) in slots
      trigger-49 .. trigger (rows up to and incl. the trigger tx) -- verify/v6_feats.py "nbuyers50".
  DL2 / DLa (GUARDS' ctx limit; DL2 = T2 windows only, DLa = T2 + re-arm): an attempt's min-out uses drop 0.15 (limit 0.85x) instead of
      0.12 when, at its SIGNING (trades seen), a wallet other than the window's whale / dumper and ours holds >= 6% of supply.
  BC  (WHO's G-cr): a window (T2 or re-arm) does not arm when the token's creator holds >= 3% at the arm (T2: rows up to the trigger;
      re-arm: rows before the arm slot) AND the creator's ledger has >= 2 of our fills with sum <= -0.05 SOL. Ledger = our live fills of
      every run BEFORE the replayed one where that creator held >= 3% at arm (VERIFY tables: T2 value scaled to 0.696 'x.s', re-arm
      'x.unit'; as forward/f0_seed_gcr.py / verify/v7_score.py), plus the replay's own fills (trade value, main basis), each usable from
      its sell's landing + 2 s.
  STo / STn (TIMING's a2 X6 t0.3): a try that would fill is BLOCKED (it fails; a later try may still fill) when a wallet holding >= 6% at
      the try's SIGNING (whale included, ours excluded) has timer hazard hz3 >= 0.3 at the send slot (P(first sell within 3 slots | held
      h slots), its positions on OTHER mints first-bought before the slot, open ones censored, >= 5 at risk; ma14_hist.py history) and
      still holds >= 6% just before the try's landing.  STn (NAIVE) also blocks with p 0.39 when such a wallet sold out between the
      signing and the landing (its token account closed: GUARDS MEASURED 39% of full dumps).
"""
import json, pickle, bisect, collections
import numpy as np

SUP = 1e15
D = "/home/moiz/sniper-data"
RUN_ORDER = ["F21", "F22", "F23", "F24", "F26", "F27", "F28", "A16", "A17", "A19", "A20", "A24", "A25", "A26", "A27", "A28", "A29", "A30", "A31", "A32",
             "A33", "A34", "A35", "A36", "A37", "A38"]
VERIFY_LABEL = {"r37": "A37", "r38f": "A38", "r38": "A38", "r39": "A39"}


class Hazard:
    """TIMING tlib.hz on the ma14_hist position table (every wallet >= 6% somewhere in the replayed runs)"""
    def __init__(self):
        z = np.load(f"{D}/multiarm/hz_pos.npz"); self.P = z["P"]
        I = json.load(open(f"{D}/multiarm/hz_ids.json")); self.Ui = {x: k for k, x in enumerate(I["user"])}; self.Mi = {x: k for k, x in enumerate(I["mint"])}
        self.UB = np.searchsorted(self.P["u"], np.arange(len(I["user"]) + 1))
        self.cache = {}

    def hz(self, wallet, S, mint, h, H=3, min_risk=5):
        key = (wallet, S, mint, h, H)
        v = self.cache.get(key)
        if v is not None: return v
        u = self.Ui.get(wallet)
        if u is None or h is None: self.cache[key] = (None, 0); return (None, 0)
        X = self.P[self.UB[u]:self.UB[u + 1]]
        X = X[:np.searchsorted(X["b0"], S)]
        X = X[X["m"] != self.Mi.get(mint, -1)]
        if len(X) == 0: self.cache[key] = (None, 0); return (None, 0)
        done = (X["s1"] >= 0) & (X["s1"] < S)
        dt = np.where(done, X["s1"] - X["b0"], S - X["b0"])
        risk = (dt >= h) & (done | (dt >= h + H)); ev = done & (dt >= h) & (dt <= h + H)
        n = int(risk.sum())
        v = ((ev.sum() + 0.05) / (n + 1.0) if n >= min_risk else None, n)
        self.cache[key] = v
        return v


def seed_ledger(run):
    """creator -> [(t_known_ms, value SOL)] from the live runs BEFORE `run` (VERIFY tables + feats)"""
    lab = VERIFY_LABEL.get(run, run)
    before = RUN_ORDER[:RUN_ORDER.index(lab)] if lab in RUN_ORDER else RUN_ORDER
    V = f"{D}/prevent/verify"
    T = pickle.load(open(f"{V}/tables.pkl", "rb")); F = pickle.load(open(f"{V}/feats.pkl", "rb"))
    tw = {(x["run"], x["w"]): x for x in T["trades"]}
    led = collections.defaultdict(list)
    for w in T["wins"]:
        if w["run"] not in before: continue
        x = tw.get((w["run"], w["w"])); f = F.get((w["run"], w["w"]), {})
        if not x or not f.get("ok") or not f.get("creator") or f.get("cre_pct", 0) < 3: continue
        led[f["creator"]].append((-1.0, x["s"] if x["kind"] == "t2" else x["unit"]))
    return led


class Filters:
    def __init__(self, name, run, tape, hazard=None):
        parts = set(name.split("+")) - {"base", ""}
        self.name = name
        self.lw = "LW" in parts
        self.dl = "all" if "DLa" in parts else ("t2" if "DL2" in parts else None)
        self.bc = "BC" in parts
        self.st = "naive" if "STn" in parts else ("open" if "STo" in parts else None)
        self.tape = tape
        self.hz = hazard if (self.st and hazard is not None) else (Hazard() if self.st else None)
        self.led = seed_ledger(run) if self.bc else None
        self.stats = collections.Counter()
        self._big = {}; self._wtr = {}

    # ---------- per-mint helpers on the ma_lib TokTL ----------
    def k_upto(self, tl, s, i):
        """number of trades with (slot, idx) <= (s, i) (all j of that tx)"""
        return bisect.bisect_right(tl.key, s * 100000 + i)

    def k_before_slot(self, tl, s): return bisect.bisect_left(tl.key, s * 100000)

    def wtrades(self, tl, g):
        """indices of wallet g's trades on the token"""
        key = (tl.mint, g)
        v = self._wtr.get(key)
        if v is None:
            v = np.nonzero(tl.user == g)[0]
            self._wtr[key] = v
        return v

    def bal_at(self, tl, g, k):
        """wallet g's balance after the token's first k trades (indices < k)"""
        ix = self.wtrades(tl, g)
        n = int(np.searchsorted(ix, k)) - 1
        return int(tl.bal_after[ix[n]]) if n >= 0 else 0

    def bigs(self, tl):
        """wallets (not ours) that ever hold >= 6% on the token"""
        v = self._big.get(tl.mint)
        if v is None:
            us = np.unique(tl.user[(tl.bal_after >= 0.06 * SUP) & ~tl.ours])
            v = [int(u) for u in us]
            self._big[tl.mint] = v
        return v

    # ---------- LW ----------
    def lw_skip(self, tl, s0, i0):
        if not self.lw or tl.n == 0: return False
        k1 = self.k_upto(tl, s0, i0); k0 = self.k_before_slot(tl, s0 - 49)
        sel = slice(k0, k1)
        m = tl.buy[sel] & ~tl.ours[sel]
        nb = len(set(tl.user[sel][m].tolist()))
        if nb <= 1: self.stats["lw_skip"] += 1; return True
        return False

    # ---------- BC ----------
    def creator_pct(self, tl, k):
        c = (self.tape.creates.get(tl.mint) or {}).get("creator")
        g = self.tape.gid.get(c) if c else None
        if g is None: return c, 0.0
        return c, self.bal_at(tl, g, k) / SUP * 100

    def bc_check(self, tl, k_cut, t):
        """-> (skip, creator, cre_pct)"""
        if not self.bc or tl.n == 0: return False, None, 0.0
        c, pct = self.creator_pct(tl, k_cut)
        if not c or pct < 3: return False, c, pct
        past = [v for tk, v in self.led.get(c, ()) if tk < t]
        if len(past) >= 2 and sum(past) <= -0.05:
            self.stats["bc_skip"] += 1
            return True, c, pct
        return False, c, pct

    def bc_add(self, creator, t_known, value):
        if self.bc and creator: self.led.setdefault(creator, []).append((t_known, value))

    # ---------- DL ----------
    def drop_for(self, kind, tl, k_sign, whale_g):
        if self.dl is None or (self.dl == "t2" and kind != "t2") or k_sign <= 0: return 0.12
        n6 = int(tl.nbig[6][k_sign - 1])
        if whale_g is not None and self.bal_at(tl, whale_g, k_sign) >= 0.06 * SUP: n6 -= 1
        if n6 > 0: self.stats["dl_deep"] += 1; return 0.15
        return 0.12

    # ---------- ST ----------
    def st_block(self, tl, k_sign, S_send, s, i, rng):
        if self.st is None or tl.n == 0: return False
        k_land = bisect.bisect_left(tl.key, s * 100000 + i)
        for g in self.bigs(tl):
            if self.bal_at(tl, g, k_sign) < 0.06 * SUP: continue
            ix = self.wtrades(tl, g)
            first = int(tl.s[ix[0]]) if len(ix) else None
            if first is None: continue
            p, n = self.hz.hz(self.tape.ids[g], int(S_send), tl.mint, int(S_send) - first, 3)
            if p is None or p < 0.3: continue
            bl = self.bal_at(tl, g, k_land)
            if bl >= 0.06 * SUP: self.stats["st_block"] += 1; return True
            if self.st == "naive" and bl <= 0.0005 * SUP and rng.random() < 0.39: self.stats["st_block_naive"] += 1; return True
        return False


def combos():
    out = []
    for lw in ("", "LW"):
        for dl in ("", "DL2", "DLa"):
            for bc in ("", "BC"):
                for st in ("", "STo", "STn"):
                    n = "+".join(x for x in (lw, dl, bc, st) if x) or "base"
                    out.append(n)
    return out
