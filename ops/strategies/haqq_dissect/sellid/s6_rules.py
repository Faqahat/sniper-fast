#!/usr/bin/env python3
"""SELLID step 6 (read-only): wallet-trigger exits, WALK-FORWARD lists, on (A) bot 247/248's own lots and (B) OUR live fills.

Lists for test day d (learned on days < d only):
  TRIG_N  wallets whose BUYS preceded a 247/248 sell (<= 212 ms) more than time x size matched chance (s4_lists.json, both bots)
  FOL_N   wallets that bought within 1 s after a 247/248 entry on the most distinct lots (= the follower bots on his dumps)
  FBOT    fbots_frozen.json (297 follower bots, frozen 10-25 22:00 PKT; in-sample before that)
  HQ      haqq's wallet (on OUR fills only: he is one of the followers we sell to)
Policies (P&L = (exit value - 1) x cost, exact curve replay of the position alone, curve P&L, tx costs excluded):
  WL(list, minsol, cap)   sell at the first outside buy >= minsol by a list wallet after the entry (reactive: lands after our
                          MEASURED trigger->sell delay quantiles, x3), else a timer sell decided at slot entry+cap
  WLW(list, cap)          the earlier of WL(list, 0, cap) and the wave exit RIDE(150, 300, 2000)
  FB(minsol, cap)         first outside buy >= minsol by ANY wallet (exit analyst's FB family) - the no-wallet control
  baselines: CUR (ours), T2 / T5 timers, MS200, wave RIDE(150,150,1000) and RIDE(150,300,2000), ACT (his own first-sell position)
His lots: precision / recall of the WL trigger vs his real first sell (trigger landing within +-212 ms of his sell).
Out: sellid/s6.txt, s6_grid.pkl"""
import pickle, sys, json, collections, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
import xlib as X
from xsim import Pos
from x7_ourexits import delays
from x12_wave import ev as ev12
OUT = "/home/moiz/sniper-data/haqq_dissect/sellid"
DAYS = (2, 3, 4, 5, 6)
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); out.append(s)


def ride_time(S, t1, s, tmax):
    bt = S.dcc[S.bu]
    rec = bt[(bt <= t1) & (bt > t1 - s)]
    if not len(rec): return t1
    later = bt[bt > t1 - s]
    gaps = np.diff(np.concatenate([later, [np.inf]]))
    j = np.argmax(gaps >= s); return min(max(later[j] + s, t1), tmax)


def lists(LOTS, ids, idm, H):
    L4 = json.load(open(f"{OUT}/s4_lists.json"))
    fb = set(idm[w] for w in json.load(open("/home/moiz/sniper/ops/strategies/presend/filter/fbots_frozen.json")) if w in idm)
    OUTL = {}
    for d in DAYS:
        for N in (25, 50, 100):
            OUTL[("TRIG", N, d)] = set(idm[w] for w in L4.get(f"BUYS_0_{d}_{N}", []) if w in idm)
        cnt = collections.Counter()
        for l in LOTS:
            if l["day"] >= d: continue
            m = l["p_bu"] & (l["p_dcc"] > 0) & (l["p_dcc"] <= 1000)
            for w in set(l["p_us"][m].tolist()): cnt[w] += 1
        for N in (25, 50, 100, 200):
            OUTL[("FOL", N, d)] = set(w for w, _ in cnt.most_common(N))
        OUTL[("FBOT", 0, d)] = fb
        OUTL[("HQ", 0, d)] = {H}
        OUTL[("FOLHQ", 50, d)] = OUTL[("FOL", 50, d)] | {H}
    return OUTL


def policies(his):
    L = [("CUR",), ("T", 2), ("T", 5), ("MS", 200), ("RIDE", 150, 150, 1000), ("RIDE", 150, 300, 2000)]
    if his: L = [("ACT",), ("T", 2), ("T", 5), ("MS", 200), ("RIDE", 150, 150, 1000), ("RIDE", 150, 300, 2000), ("RIDE", 424, 1000, 20000)]
    for x in (0.0, 0.3, 1.0):
        for cap in (2, 3, 5, 8): L.append(("FB", x, cap))
    lsts = [("TRIG", 25), ("TRIG", 50), ("TRIG", 100), ("FOL", 25), ("FOL", 50), ("FOL", 100), ("FOL", 200), ("FBOT", 0)]
    if not his: lsts += [("HQ", 0), ("FOLHQ", 50)]
    for ln in lsts:
        for x in (0.0, 0.3):
            for cap in (2, 3, 5, 8): L.append(("WL", ln, x, cap))
        for cap in (5, 10): L.append(("WLW", ln, cap))
    return L


def evaluate(S, pol, DR, DT, kind, LST, d, act_q=None):
    """returns (value ratio, trigger chain-clock time or None)"""
    k = pol[0]
    if S.n == 0: return S.v_pre, None
    if k == "ACT": return float(S.val_q(act_q)), None
    if k in ("CUR", "T", "MS", "RIDE"): return ev12(S, pol, DR, DT), None
    dt = DT[kind]
    if k == "FB":
        _, x, cap = pol; j = S.first(S.bu & (S.sol >= x))
        tN = S.slot_start(cap)
        if j is not None and S.dcc[j] < tN: return S.land_val(S.dcc[j], DR), S.dcc[j]
        return S.timer_val(cap, dt), None
    lst = LST[(pol[1][0], pol[1][1], d)]
    inl = np.isin(S.p["us"], list(lst)) if lst else np.zeros(S.n, bool)
    if k == "WL":
        _, ln, x, cap = pol; j = S.first(S.bu & inl & (S.sol >= x))
        tN = S.slot_start(cap)
        if j is not None and S.dcc[j] < tN: return S.land_val(S.dcc[j], DR), S.dcc[j]
        return S.timer_val(cap, dt), None
    if k == "WLW":
        _, ln, cap = pol; j = S.first(S.bu & inl)
        tw = ride_time(S, 150, 300, 2000)
        if j is not None and S.dcc[j] < min(tw, S.slot_start(cap)): return S.land_val(S.dcc[j], DR), S.dcc[j]
        return S.land_val(tw, DR), None
    raise ValueError(pol)


def main():
    t0 = time.time()
    Z = pickle.load(open(f"{OUT}/s1.pkl", "rb")); LOTS = Z["lots"]; H = Z["H"]
    ids = json.load(open("/home/moiz/sniper-data/dv8/tab/ids.json")); idm = {k: i for i, k in enumerate(ids)}
    LST = lists(LOTS, ids, idm, H)
    print(f"lists built ({time.time() - t0:.0f}s)", flush=True)
    DR, DT, nd = delays()
    P("# Wallet-trigger exits, walk-forward lists (learned on days < test day), exact replay, MEASURED sell delays (curve P&L)")
    P(f"reactive delay quantiles (ms): {' '.join(f'{x:.0f}' for x in DR)}")
    # list overlaps
    for d in DAYS:
        a = LST[("FOL", 50, d)]; b = LST[("TRIG", 50, d)]; c = LST[("FBOT", 0, d)]
        P(f"- D{d}: FOL50 & FBOT {len(a & c)}, FOL50 & TRIG50 {len(a & b)}, TRIG50 & FBOT {len(b & c)}; TRIG50 size {len(b)}")
    G = {}
    # ---------- (A) his lots
    PH = policies(True)
    HL = [l for l in LOTS if l["first_sell_k"] is not None and l["day"] in DAYS and len(l["p_dcc"])]
    meta = []
    for fol in (1.0, 0.9):
        M = np.zeros((len(PH), len(HL))); TR = np.full((len(PH), len(HL)), np.nan)
        for b, l in enumerate(HL):
            p = dict(dcc=l["p_dcc"].astype(np.float64), bu=l["p_bu"], so=l["p_so"], tk=l["p_tk"], us=l["p_us"], V0=l["V0"], T0=l["T0"], sin=l["sin"],
                     cost=l["cost"], fee=l["fee"], off_in_slot=l["off_in_slot"], kind="reg")
            S = Pos(p, fol)
            for a, pol in enumerate(PH):
                v, tr = evaluate(S, pol, DR, DT, "reg", LST, l["day"], act_q=l["n_before_sell"] - 1)
                M[a, b] = (v - 1) * S.cost
                if tr is not None: TR[a, b] = tr
            if fol == 1.0: meta.append((l["code"], l["day"], l["net"], l["sell_dcc"]))
        G[("his", fol)] = (M, TR)
        print(f"his lots fol {fol} done ({time.time() - t0:.0f}s)", flush=True)
    code = np.array([m[0] for m in meta]); day = np.array([m[1] for m in meta]); real = np.array([m[2] for m in meta]); Ts = np.array([m[3] for m in meta])
    M1, TR1 = G[("his", 1.0)]; M9, _ = G[("his", 0.9)]
    med = float(np.median(DR))
    for c in (247, 248):
        mk = code == c
        P(f"\n## (A) bot {c}'s own lots, test days D2-D6 ({mk.sum():,} lots): realized (his whole exit, curve) {real[mk].sum():+.2f} SOL")
        P("| policy | SOL | mSOL/lot | 10% fewer followers | " + " | ".join(f"D{d}" for d in DAYS) + " | rule-triggered | precision | recall |")
        P("|---|---|---|---|" + "---|" * len(DAYS) + "---|---|---|")
        tot = M1[:, mk].sum(1); o = np.argsort(-tot)
        show = [PH.index(x) for x in PH if x[0] in ("ACT", "T", "MS", "RIDE")]
        best_wl = [a for a in o if PH[a][0] in ("WL", "WLW", "FB")][:20]
        for a in show + best_wl:
            tr = TR1[a, mk]; trig = ~np.isnan(tr)
            hit = trig & (np.abs(tr + med - Ts[mk]) <= 212)
            prec = hit.sum() / max(trig.sum(), 1); rec = hit.sum() / mk.sum()
            P(f"| {PH[a]} | {tot[a]:+.2f} | {1000 * tot[a] / mk.sum():+.2f} | {M9[a, mk].sum():+.2f} | " + " | ".join(f"{M1[a, mk & (day == d)].sum():+.2f}" for d in DAYS) +
              f" | {trig.mean():.2f} | {prec:.3f} | {rec:.3f} |")
    # ---------- (B) our fills
    O = pickle.load(open(f"{OUT}/ourpaths_us.pkl", "rb"))
    PO = policies(False)
    for fol in (1.0, 0.9):
        M = np.zeros((len(PO), len(O)))
        for b, p in enumerate(O):
            S = Pos(p, fol)
            for a, pol in enumerate(PO):
                if p["day"] not in DAYS: continue
                v, _ = evaluate(S, pol, DR, DT, p["kind"], LST, p["day"])
                M[a, b] = (v - 1) * S.cost
        G[("ours", fol)] = M
        print(f"our fills fol {fol} done ({time.time() - t0:.0f}s)", flush=True)
    kinds = np.array([p["kind"] for p in O]); days = np.array([p["day"] for p in O]); realo = np.array([p["realized"] for p in O])
    M1 = G[("ours", 1.0)]; M9 = G[("ours", 0.9)]
    for kind in ("ps", "reg"):
        mk = (kinds == kind) & np.isin(days, DAYS); dl = sorted(set(days[mk].tolist()))
        P(f"\n## (B) OUR {kind} fills ({mk.sum()}), realized {realo[mk].sum():+.3f} SOL")
        P("| policy | SOL | mSOL/fill [90%] | 10% fewer followers | " + " | ".join(f"D{d}" for d in dl) + " | vs wave RIDE(150," + ("150,1000" if kind == "ps" else "300,2000") + ") per day |")
        P("|---|---|---|---|" + "---|" * len(dl) + "---|")
        tot = M1[:, mk].sum(1); o = np.argsort(-tot)
        wv = PO.index(("RIDE", 150, 150, 1000) if kind == "ps" else ("RIDE", 150, 300, 2000))
        show = [PO.index(x) for x in PO if x[0] in ("CUR", "T", "MS", "RIDE")]
        rest = [a for a in o if PO[a][0] in ("WL", "WLW", "FB")][:25]
        for a in show + rest:
            lo, hi = X.boot_sum(M1[a, mk] - 0, 2000)
            dd = [M1[a, mk & (days == d)].sum() - M1[wv, mk & (days == d)].sum() for d in dl]
            P(f"| {PO[a]} | {tot[a]:+.3f} | {1000 * tot[a] / mk.sum():+.2f} [{1000 * lo / mk.sum():+.2f}..{1000 * hi / mk.sum():+.2f}] | {M9[a, mk].sum():+.3f} | " +
              " | ".join(f"{M1[a, mk & (days == d)].sum():+.3f}" for d in dl) + " | " + " ".join(f"{x:+.3f}" for x in dd) + " |")
    pickle.dump(dict(PH=PH, PO=PO, G=G, meta=meta, ometa=[(p["kind"], p["day"], p["realized"]) for p in O]), open(f"{OUT}/s6_grid.pkl", "wb"))
    open(f"{OUT}/s6.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
