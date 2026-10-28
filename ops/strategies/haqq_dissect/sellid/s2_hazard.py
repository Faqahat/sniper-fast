#!/usr/bin/env python3
"""SELLID step 2 (read-only): does a SPECIFIC wallet's trade make bot 247 / 248 sell right after it? (hazard-style)

Unit = one outside trade j (buy or sell) that lands while a 247/248 lot is open (after the buy, before the lot's FIRST sell).
  y_j = 1 if the lot's first sell lands within W ms after j (chain clock), W = 212 (one slot) [also 100 and 424 in the table].
Expected E_j = mean y of all trades in the same stratum (code x side x time-since-entry bucket x trade-size bucket), i.e. what a
  random trade at the same moment of the hold and of the same size gets ("matched random moments in the same kind of lot").
Per key (wallet+side, or identical-size buy cluster): n, lots, sum y, sum E, lift = sum y / sum E, per-day lifts.
Also: the trade immediately before each first sell (same slot? idx gap) by wallet class; known lists (fbots_frozen, cohort_train,
  named dip bots, our wallets, haqq's other codes).
Out: sellid/s2.txt, s2_units.npz (units for the walk-forward)"""
import pickle, sys, json, collections, time
import numpy as np
OUT = "/home/moiz/sniper-data/haqq_dissect/sellid"
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
import xlib as X
TB = np.array([0, 1, 2, 3, 4, 5, 8, 15, 30, 10 ** 6])            # slot buckets since entry
SB = np.array([0, 0.05, 0.1, 0.3, 0.6, 1.0, 2.0, 4.0, 1e9])        # SOL buckets
NAMED = {"DF7eRX": "DF7eRX", "9pQQc1": "9pQQc1", "6anjqM": "6anjqM", "EMKY7r": "EMKY7r", "AJ5snx": "AJ5snx", "HkQ7hM": "HkQ7hMjy",
         "DYXDDr": "DYXDDrZC", "CZ77on": "CZ77onJz", "6VzXcL": "6VzXcLk9"}
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); out.append(s)


def lists(ids, idm):
    fb = set(idm[w] for w in json.load(open("/home/moiz/sniper/ops/strategies/presend/filter/fbots_frozen.json")) if w in idm)
    co = set(idm[w] for w in json.load(open("/home/moiz/sniper/ops/overnight/sel/cohort_train.json")) if w in idm)
    named = {}
    for i, w in enumerate(ids):
        p = w[:6]
        if p in NAMED: named[i] = NAMED[p]
    return fb, co, named


def main():
    t0 = time.time()
    Z = pickle.load(open(f"{OUT}/s1.pkl", "rb")); LOTS = Z["lots"]; OURS = set(Z["OURS"])
    ids = json.load(open("/home/moiz/sniper-data/dv8/tab/ids.json")); idm = {k: i for i, k in enumerate(ids)}
    fb, co, named = lists(ids, idm)
    P(f"# Bot 247/248 sells vs specific outside wallets (hazard, MEASURED), lots {len(LOTS):,}; fbots {len(fb)}, cohort {len(co)}, named dip bots found {sorted(set(named.values()))}")
    rows = collections.defaultdict(list)
    for l in LOTS:
        if l["first_sell_k"] is None: continue
        ts = l["sell_dcc"]; m = l["p_dcc"] < ts
        if not m.any(): continue
        d = l["p_dcc"][m].astype(np.float64)
        gap = ts - d
        rows["code"].append(np.full(m.sum(), l["code"], np.int16)); rows["lot"].append(np.full(m.sum(), l["id"], np.int32))
        rows["day"].append(np.full(m.sum(), l["day"], np.int8)); rows["us"].append(l["p_us"][m]); rows["bu"].append(l["p_bu"][m])
        rows["so"].append(l["p_so"][m]); rows["dsl"].append(l["p_dsl"][m]); rows["dcc"].append(d); rows["gap"].append(gap)
        rows["last"].append(np.arange(m.sum()) == m.sum() - 1)
        # same slot as the sell?
        rows["sslot"].append(l["p_dsl"][m] == (l["p_dsl"][m][-1] if False else 0))
    U = {k: np.concatenate(v) for k, v in rows.items()}
    n = len(U["us"])
    tb = np.searchsorted(TB, U["dsl"], side="right") - 1; sb = np.searchsorted(SB, U["so"], side="right") - 1
    U["tb"] = tb.astype(np.int8); U["sb"] = sb.astype(np.int8)
    np.savez(f"{OUT}/s2_units.npz", **U)
    P(f"units (outside trades while a lot is open): {n:,} ({time.time() - t0:.0f}s)")
    for W in (100, 212, 424):
        y = (U["gap"] <= W).astype(np.float64)
        P(f"- W={W} ms: P(first sell within W after a trade) buys {y[U['bu']].mean():.4f}, sells {y[~U['bu']].mean():.4f}")
    W = 212
    y = (U["gap"] <= W).astype(np.float64)
    strat = ((U["code"] - 247).astype(np.int64) * 2 + U["bu"]) * 100 + tb * 10 + sb
    us_, inv = np.unique(strat, return_inverse=True)
    sm = np.bincount(inv, y) / np.bincount(inv)
    E = sm[inv]
    # size-free strata (only code x side x time), to see if size explains it
    strat2 = ((U["code"] - 247).astype(np.int64) * 2 + U["bu"]) * 100 + tb * 10
    _, inv2 = np.unique(strat2, return_inverse=True); E2 = (np.bincount(inv2, y) / np.bincount(inv2))[inv2]
    P("\n## Size effect alone: P(first sell within 212 ms) by outside BUY size (both bots, time-standardised lift)")
    P("| buy SOL | n | rate | lift vs time-matched |"); P("|---|---|---|---|")
    for b in range(len(SB) - 1):
        mm = U["bu"] & (sb == b)
        if mm.sum(): P(f"| {SB[b]:g}-{SB[b + 1]:g} | {mm.sum():,} | {y[mm].mean():.4f} | {y[mm].sum() / E2[mm].sum():.2f} |")
    # per wallet+side
    for code in (247, 248):
        for side in (1, 0):
            mm = (U["code"] == code) & (U["bu"] == side)
            if not mm.any(): continue
            w = U["us"][mm]; yy = y[mm]; ee = E[mm]; e2 = E2[mm]; dd = U["day"][mm]; lt = U["lot"][mm]
            uw, iw = np.unique(w, return_inverse=True)
            N = np.bincount(iw); Y = np.bincount(iw, yy); EE = np.bincount(iw, ee); EE2 = np.bincount(iw, e2)
            nl = np.array([0] * len(uw))
            ok = (N >= 40) & (Y >= 8)
            P(f"\n## bot {code}: outside {'BUYS' if side else 'SELLS'} -> his sell within 212 ms. base rate {yy.mean():.4f}; wallets with n>=40 & y>=8: {ok.sum()} of {len(uw):,}")
            P("| wallet | class | n trades | followed | rate | lift (time+size matched) | lift (time only) | per-day lift D0..D6 (n) |"); P("|---|---|---|---|---|---|---|---|")
            o = np.argsort(-(Y / np.maximum(EE, 1e-9)) * ok)
            shown = 0
            for a in o:
                if not ok[a]: continue
                wid = int(uw[a]); cls = ("OURS" if wid in OURS else named.get(wid, "") + ("fbot " if wid in fb else "") + ("cohort" if wid in co else "")) or "-"
                pd = []
                for dd_ in range(7):
                    q = (w == wid) & (dd == dd_)
                    if q.sum() >= 5: pd.append(f"{yy[q].sum() / max(ee[q].sum(), 1e-9):.1f}({q.sum()})")
                    else: pd.append("·")
                P(f"| {ids[wid][:8]} | {cls} | {N[a]:,} | {int(Y[a])} | {Y[a] / N[a]:.3f} | {Y[a] / EE[a]:.2f} | {Y[a] / EE2[a]:.2f} | {' '.join(pd)} |")
                shown += 1
                if shown >= 25: break
            # classes
            P(f"\n### bot {code} {'buys' if side else 'sells'} by wallet class (lift time+size matched)")
            for cname, f in (("our wallets", lambda x: x in OURS), ("fbots_frozen", lambda x: x in fb), ("cohort_train", lambda x: x in co),
                             ("named dip bots", lambda x: x in named), ("other", lambda x: x not in OURS and x not in fb and x not in co and x not in named)):
                q = np.array([f(int(x)) for x in uw])
                P(f"- {cname}: wallets {q.sum():,}, trades {N[q].sum():,}, followed {int(Y[q].sum()):,}, lift {Y[q].sum() / max(EE[q].sum(), 1e-9):.2f}")
            # concentration: share of followed events explained by top wallets
            ordr = np.argsort(-Y)
            P(f"- followed events {int(Y.sum()):,}; top-10 wallets by count hold {Y[ordr[:10]].sum() / max(Y.sum(), 1):.2%}, top-50 {Y[ordr[:50]].sum() / max(Y.sum(), 1):.2%}")
    # identical-size buy clusters
    P("\n## Identical-size outside buys (SOL rounded to 0.001) -> his sell within 212 ms, size clusters with n>=100 (both bots)")
    mm = U["bu"]
    key = np.round(U["so"][mm], 3); yy = y[mm]; ee = E[mm]
    uk, ik = np.unique(key, return_inverse=True); N = np.bincount(ik); Y = np.bincount(ik, yy); EE = np.bincount(ik, ee)
    nw = collections.defaultdict(set)
    for kk, ww in zip(ik.tolist(), U["us"][mm].tolist()): nw[kk].add(ww)
    o = np.argsort(-N)
    P("| size SOL | n | wallets | followed | lift |"); P("|---|---|---|---|---|")
    for a in o[:25]:
        P(f"| {uk[a]:.3f} | {N[a]:,} | {len(nw[a]):,} | {int(Y[a])} | {Y[a] / max(EE[a], 1e-9):.2f} |")
    open(f"{OUT}/s2.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
