#!/usr/bin/env python3
"""QUIET4 step 3: every candidate skip rule, scored as an ADDITION on top of the live r49/r50 config (QUIET + QUIET3-A + creator
ledger 2:0.05; positions those would have blocked are already removed, q4lib.baseline). Sequential and kept-only: a rule's ledgers
learn only from positions the rule itself kept, and only once the position's label was known (closed) before the new trigger.
Money = the blocked positions' real realized P&L (each run at its own exit). Prints one row per rule; writes grid.json.
  --sel   print only the DEV-ranked selection table (DEV saved > 0 and DEV w/o top 5 > 0), then VAL / HOLD / R50 next to it"""
import sys, json, pickle, collections, itertools, math
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/quiet4")
import q4lib as L

X = pickle.load(open(f"{L.D}/feats.pkl", "rb")); P, F, H = X["P"], X["F"], X["H"]
FB = {f["id"]: f for f in F}
RB = {}
try: RB = pickle.load(open(f"{L.D}/recent_book.pkl", "rb"))     # x4: recent DumpBook features per position id (covered periods only)
except FileNotFoundError: pass


def arm_holders(p, pct_min):
    """wallets holding >= pct_min at the arm: re-arm = the arm record's holders; T2 = fill-time holders with hold age >= fill - trigger
    slots (they held at the trigger; PROXY for the engine's holder map at the arm); + the creator (ann.cr_pct). Whale excluded."""
    hs = {}
    if p["kind"] != "T2":
        for x in p["arm_holders"] or []: hs[x["w"]] = x["pct"]
    elif p["fill_holders"] is not None and p["fill_slot"] and p["trig_slot"]:
        lag = p["fill_slot"] - p["trig_slot"]
        for x in p["fill_holders"]:
            if (x.get("age") or 0) >= lag: hs[x["w"]] = x["pct"]
    if p["creator"] and (p["cr_pct"] or 0) > 0: hs[p["creator"]] = max(hs.get(p["creator"], 0), p["cr_pct"])
    hs.pop(p["whale"], None)
    return {w: v for w, v in hs.items() if v >= pct_min and w not in L.OURS}


class State:
    def __init__(self): self.whale = collections.defaultdict(list); self.ent = collections.defaultdict(list); self.sell = collections.defaultdict(list); self.cre = collections.defaultdict(list)
    def add(self, q):
        if q["whale"]: self.whale[q["whale"]].append(q)
        if q["creator"]: self.cre[q["creator"]].append(q)
        roles = set(arm_holders(q, 3.0)) | ({q["whale"]} if q["whale"] else set())
        for w in roles: self.ent[w].append(q)
        for u, sol in q["hold_sellers"].items():
            if sol >= 0.3 and u not in L.OURS: self.sell[u].append(q)


def simulate(rule):
    S = State(); pend = []; blocked = set(); kq = []
    import heapq
    for p in P:
        while kq and kq[0][0] < p["t0"]:
            _, _, q = heapq.heappop(kq); S.add(q)
        if rule(p, FB[p["id"]], S): blocked.add(p["id"])
        else: heapq.heappush(kq, (p["known"], p["id"], p))
    return blocked


# ---------------- rule families ----------------
def r_whale_unf(k, hh):
    def f(p, ft, S):
        h = [q for q in S.whale.get(p["whale"], []) if hh is None or q["known"] >= p["t0"] - hh * 3.6e12][-k:]
        return len(h) >= 1 and all(not q["followed"] for q in h)
    return f
def r_whale_unf_n(k, hh):          # needs a full k
    def f(p, ft, S):
        h = [q for q in S.whale.get(p["whale"], []) if hh is None or q["known"] >= p["t0"] - hh * 3.6e12][-k:]
        return len(h) >= k and all(not q["followed"] for q in h)
    return f
def r_whale_dumped(n, hh, sol):
    """the trigger whale / dumper SOLD >= sol into our hold on >= n of our earlier kept positions (any creator, any role on those)"""
    def f(p, ft, S):
        if not p["whale"]: return False
        h = [q for q in S.sell.get(p["whale"], []) if (hh is None or q["known"] >= p["t0"] - hh * 3.6e12) and q["hold_sellers"].get(p["whale"], 0) >= sol]
        return len(h) >= n
    return f
def r_whale_sum(n, s, hh):
    def f(p, ft, S):
        h = [q for q in S.whale.get(p["whale"], []) if hh is None or q["known"] >= p["t0"] - hh * 3.6e12]
        return len(h) >= n and sum(q["pnl"] for q in h) <= -s
    return f
def r_whale_folrate(k, hh, mx):
    def f(p, ft, S):
        h = [q for q in S.whale.get(p["whale"], []) if q["known"] >= p["t0"] - hh * 3.6e12][-k:]
        return len(h) >= k and sum(q["followed"] for q in h) / len(h) <= mx
    return f
def r_creator_recent_unf(k, hh):
    def f(p, ft, S):
        if not p["creator"]: return False
        h = [q for q in S.cre.get(p["creator"], []) if q["known"] >= p["t0"] - hh * 3.6e12][-k:]
        return len(h) >= k and all(not q["followed"] for q in h)
    return f
def r_entity(pct, n, s, src, hh=None):
    """bad-actor ledger: a wallet (arm holder >= pct, or the creator, or the trigger whale/dumper) whose ledger has >= n positions summing
    <= -s. src 'ent' = positions where it was a >= 3% holder / creator / whale; 'sell' = positions where it SOLD >= 0.3 SOL into our hold"""
    def f(p, ft, S):
        ws = set(arm_holders(p, pct)) | ({p["whale"]} if p["whale"] else set())
        book = S.ent if src == "ent" else S.sell
        for w in ws:
            h = [q for q in book.get(w, []) if hh is None or q["known"] >= p["t0"] - hh * 3.6e12]
            if len(h) >= n and sum(q["pnl"] for q in h) <= -s: return True
        return False
    return f
def r_seller_present(n, hh, pct, minsol):
    """a REPEAT HOLD-SELLER (sold >= minsol into our hold on >= n earlier kept positions in the window) holds >= pct at the arm"""
    def f(p, ft, S):
        for w in arm_holders(p, pct):
            h = [q for q in S.sell.get(w, []) if (hh is None or q["known"] >= p["t0"] - hh * 3.6e12) and q["hold_sellers"].get(w, 0) >= minsol]
            if len(h) >= n: return True
        return False
    return f
def r_ws(win_key, fills, mx):
    def f(p, ft, S):
        v = ft.get(win_key)
        return v is not None and ft[win_key + "_k"] >= fills and v <= mx
    return f
def r_bait(nmin, dmax, tmpl=False):
    def f(p, ft, S):
        if p["kind"] != "T2": return False
        wd = (p["quiet"] or {}).get("wh_dumps")
        return ft["ws24_n"] >= nmin and wd is not None and wd <= dmax and (not tmpl or ft["tmpl"])
    return f
def r_q3a_var(nmax, dmax):
    """QUIET3-A widened: T2, n_120s <= nmax and wh_dumps <= dmax (what it adds beyond the live 15/3)"""
    def f(p, ft, S):
        if p["kind"] != "T2": return False
        v, q = p["v2"] or {}, p["quiet"] or {}
        n, wd = v.get("n_120s"), q.get("wh_dumps")
        return n is not None and wd is not None and q.get("rule_on") is not False and n <= nmax and wd <= dmax
    return f
def r_quiet_shrink(m, prior, fol=4.0, kinds=("T2",)):
    """QUIET with a shrunk signal 4: wh_fol' = (wh_fol * n + prior * m) / (n + m) (n = wh_dumps; none = prior); skip when signals 1-3
    hold and wh_fol' < fol"""
    def f(p, ft, S):
        if p["kind"] not in kinds: return False
        q = p["quiet"] or {}
        fl = q.get("q")
        if not fl or q.get("rule_on") is False or not (fl[0] and fl[1] and fl[2]): return False
        n = q.get("wh_dumps") or 0; wf = q.get("wh_fol")
        if wf is None: return False
        ws = prior if n == 0 else (wf * n + prior * m) / (n + m)
        return ws < fol
    return f
def r_quiet_minn(nmin, fol=4.0, kinds=("T2",)):
    """QUIET: signal 4 counts as 'followed' only with >= nmin dumps"""
    def f(p, ft, S):
        if p["kind"] not in kinds: return False
        q = p["quiet"] or {}; fl = q.get("q")
        if not fl or q.get("rule_on") is False or not (fl[0] and fl[1] and fl[2]): return False
        return (q.get("wh_dumps") or 0) < nmin or (q.get("wh_fol") or -1) < fol
    return f
def r_recent_book(key, nmin, mx, kinds=("T2",)):
    """recent DumpBook follower rate of the whale (x4): mean followers of its dumps in the window (needs >= nmin dumps) <= mx;
    only on positions whose period the recording covers (else not decidable = not blocked)"""
    def f(p, ft, S):
        if p["kind"] not in kinds: return False
        r = RB.get(p["id"])
        if not r or r.get(key) is None: return False
        n, m = r[key]
        return n >= nmin and m <= mx
    return f
def r_recent_book_quiet(key, nmin, fol, kinds=("T2",)):
    """QUIET with signal 4 recomputed on the RECENT window: skip when signals 1-3 hold and the recent mean < fol (or < nmin dumps)"""
    def f(p, ft, S):
        if p["kind"] not in kinds: return False
        q = p["quiet"] or {}; fl = q.get("q")
        if not fl or q.get("rule_on") is False or not (fl[0] and fl[1] and fl[2]): return False
        r = RB.get(p["id"])
        if not r or r.get(key) is None: return False
        n, m = r[key]
        return n < nmin or m < fol
    return f
def r_regime_quiet(key, mx, nmax, extra=None):
    """bad market regime (gauge <= mx) AND a quiet T2 token (n_120s <= nmax) [AND extra: 'q2' = QUIET signals 1-3 true]"""
    def f(p, ft, S):
        if p["kind"] != "T2": return False
        v = ft.get(key); n = (p["v2"] or {}).get("n_120s")
        if v is None or n is None or v > mx or n > nmax: return False
        if extra == "q13":
            fl = (p["quiet"] or {}).get("q") or [False] * 4
            return fl[0] and fl[2]
        return True
    return f
def r_regime(key, mx):
    def f(p, ft, S):
        v = ft.get(key); return v is not None and v <= mx
    return f


RULES = {}
for k, hh in itertools.product((1, 2, 3, 4), (1, 3, 6, 24, None)):
    RULES[f"whale last<={k} unf ({hh or 'all'}h)"] = r_whale_unf(k, hh)
    RULES[f"whale last=={k} unf ({hh or 'all'}h)"] = r_whale_unf_n(k, hh)
for n, s, hh in itertools.product((2, 3, 5), (0.03, 0.05, 0.1, 0.2), (3, 24, None)):
    RULES[f"whale sum n>={n} <=-{s} ({hh or 'all'}h)"] = r_whale_sum(n, s, hh)
for k, hh, mx in itertools.product((3, 5, 8), (1, 3, 6), (0.34, 0.5, 0.6)):
    RULES[f"whale fol-rate last{k} {hh}h <={mx}"] = r_whale_folrate(k, hh, mx)
for k, hh in itertools.product((1, 2, 3), (1, 3, 6)):
    RULES[f"creator recent last=={k} unf {hh}h"] = r_creator_recent_unf(k, hh)
for pct, n, s, src, hh in itertools.product((3, 5, 8), (2, 3, 5), (0.05, 0.1, 0.2, 0.3), ("ent", "sell"), (24, None)):
    RULES[f"entity {src} pct>={pct} n>={n} <=-{s} ({hh or 'all'}h)"] = r_entity(pct, n, s, src, hh)
for wk, fills, mx in itertools.product(("ws3_mean", "ws6_mean", "ws24_mean"), (2, 3, 5, 8), (-0.005, -0.01, -0.015, -0.02, -0.03)):
    RULES[f"whale shadow {wk[2:-5]}h fills>={fills} mean<={mx}"] = r_ws(wk, fills, mx)
for n, hh, pct, sol in itertools.product((2, 3, 5), (6, 24, None), (2, 3, 5), (0.3, 0.8)):
    RULES[f"repeat hold-seller n>={n} sol>={sol} holds>={pct}% ({hh or 'all'}h)"] = r_seller_present(n, hh, pct, sol)
for n, hh, sol in itertools.product((1, 2, 3), (3, 24, None), (0.3, 1.0, 3.0)):
    RULES[f"whale dumped-on-us n>={n} sol>={sol} ({hh or 'all'}h)"] = r_whale_dumped(n, hh, sol)
for nmin, dmax in itertools.product((3, 5, 10, 20), (0, 3, 10)):
    RULES[f"bait ws24_n>={nmin} wh_dumps<={dmax}"] = r_bait(nmin, dmax)
    RULES[f"bait ws24_n>={nmin} wh_dumps<={dmax} tmpl"] = r_bait(nmin, dmax, True)
for nmax, dmax in itertools.product((7, 10, 15, 20, 30), (3, 4, 5, 6, 8, 10)):
    RULES[f"q3a widened n120<={nmax} whd<={dmax}"] = r_q3a_var(nmax, dmax)
for m, prior in itertools.product((2, 4, 8, 16), (0.0, 1.0, 2.0, 3.0)):
    RULES[f"quiet shrink m={m} prior={prior} T2"] = r_quiet_shrink(m, prior)
    RULES[f"quiet shrink m={m} prior={prior} T2+re"] = r_quiet_shrink(m, prior, kinds=("T2", "rearm"))
for nmin in (3, 5, 8, 10, 20):
    RULES[f"quiet min-dumps {nmin} T2"] = r_quiet_minn(nmin)
for key, mx in itertools.product(("rg_fol20", "rg_fol50"), (0.6, 0.65, 0.7)):
    RULES[f"regime {key}<={mx}"] = r_regime(key, mx)
for mx in (-0.005, -0.01):
    RULES[f"regime rg_sh60<={mx}"] = r_regime("rg_sh60", mx)
for key, mx in itertools.product(("rg_sh3h", "rg_sh200"), (-0.01, -0.005, 0.0, 0.005)):
    RULES[f"regime {key}<={mx}"] = r_regime(key, mx)
    for nmax in (7, 10, 15, 30):
        RULES[f"regime {key}<={mx} & n120<={nmax}"] = r_regime_quiet(key, mx, nmax)
        RULES[f"regime {key}<={mx} & n120<={nmax} & q1,q3"] = r_regime_quiet(key, mx, nmax, "q13")
for key in ("rb1h", "rb3h", "rb6h", "rbl5", "rbl10"):
    for nmin, mx in itertools.product((3, 5), (1.0, 2.0, 3.0)):
        RULES[f"recent book {key} n>={nmin} mean<={mx}"] = r_recent_book(key, nmin, mx)
    for nmin, fol in itertools.product((1, 3, 5), (2.0, 3.0, 4.0)):
        RULES[f"QUIET sig4 on recent {key} n>={nmin} fol<{fol}"] = r_recent_book_quiet(key, nmin, fol)


def run(names=None):
    res = {}
    for name, rule in RULES.items():
        if names and name not in names: continue
        if (name.startswith("recent book") or name.startswith("QUIET sig4")) and not RB: continue
        b = simulate(rule)
        row = {}
        for per in L.PERS:
            row[per] = L.summ([p for p in P if p["per"] == per and p["id"] in b], H, per)
        # per-run saves
        row["runs"] = {r: round(-sum(p["pnl"] for p in P if p["run"] == r and p["id"] in b), 4) for r in L.RUNS}
        row["blocked_ids"] = sorted(b)
        res[name] = row
    return res


def fmt(name, row):
    s = f"{name:<52}"
    for per in L.PERS:
        d = row[per]
        s += f" | {per} {d['n']:3d} w{d['nw']:3d} {d['w']:+.2f} l{d['nl']:3d} {d['l']:+.2f} ={d['saved']:+.3f} w5 {d['wo5']:+.3f} {d['day']:+.2f}/d"
    return s


if __name__ == "__main__":
    res = run()
    json.dump(res, open(f"{L.D}/grid.json", "w"))
    rows = sorted(res.items(), key=lambda kv: -kv[1]["DEV"]["saved"])
    print(f"{len(res)} rules. DEV-ranked (DEV saved > 0 and DEV w/o top5 > 0 first); VAL/HOLD/R50 shown for the confirm step")
    for name, row in rows:
        if row["DEV"]["saved"] > 0 and row["DEV"]["wo5"] > 0 and row["DEV"]["n"] >= 3: print(fmt(name, row))
