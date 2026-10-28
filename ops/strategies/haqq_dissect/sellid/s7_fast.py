#!/usr/bin/env python3
"""SELLID step 7 (read-only): bot 247's (and 248's) fast winners (first sell < 1 s) vs 4-8 s holds, using ONLY what is on the tape
in the first t_obs ms after his buy (t_obs = 400 ms ~ his 2-slot minimum hold, and 800 ms), plus entry context (bots/b1.pkl).
Features (outside rows only, haqq rows removed; lot replay value from the exact curve of the lot alone):
  nb, bsol, maxb, nbw (distinct buyers), nfol (FOL-50 follower wallets, walk-forward list from s6), nfb (fbots_frozen), ns, ssol,
  v_t (lot value / cost at t_obs), vmax_t, last_gap (ms since the last outside buy at t_obs), hq_other (another haqq code bought in
  the window), dump drop / SOL, trades ahead (d_nbuy), curve SOL, age.
Tables: group means; walk-forward AUC of a small GBDT (train days < d) for 'fast winner' vs '4-8 s'; P&L of each group under
his exit, MS(400/800/1000), wave RIDE(424,1000,20000), with our measured delays.
Out: sellid/s7.txt"""
import pickle, sys, json, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
import xlib as X
from xsim import Pos
from x7_ourexits import delays
from x12_wave import ev as ev12
OUT = "/home/moiz/sniper-data/haqq_dissect/sellid"
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); out.append(s)


def main():
    Z = pickle.load(open(f"{OUT}/s1.pkl", "rb")); LOTS = Z["lots"]; H = Z["H"]
    ids = json.load(open("/home/moiz/sniper-data/dv8/tab/ids.json")); idm = {k: i for i, k in enumerate(ids)}
    fb = set(idm[w] for w in json.load(open("/home/moiz/sniper/ops/strategies/presend/filter/fbots_frozen.json")) if w in idm)
    B1 = pickle.load(open("/home/moiz/sniper-data/haqq_dissect/bots/b1.pkl", "rb"))
    ctx = {(r["mi"], r["slot"], r["idx"]): r for r in B1}
    # walk-forward FOL50 per day (same definition as s6)
    FOL = {}
    for d in range(0, 7):
        cnt = collections.Counter()
        for l in LOTS:
            if l["day"] >= d: continue
            m = l["p_bu"] & (l["p_dcc"] > 0) & (l["p_dcc"] <= 1000)
            for w in set(l["p_us"][m].tolist()): cnt[w] += 1
        FOL[d] = set(w for w, _ in cnt.most_common(50))
    DR, DT, _ = delays()
    rows = []
    for l in LOTS:
        if l["first_sell_k"] is None or not len(l["p_dcc"]): continue
        hold = l["sell_dcc"]
        p = dict(dcc=l["p_dcc"].astype(np.float64), bu=l["p_bu"], so=l["p_so"], tk=l["p_tk"], us=l["p_us"], V0=l["V0"], T0=l["T0"], sin=l["sin"],
                 cost=l["cost"], fee=l["fee"], off_in_slot=l["off_in_slot"], kind="reg")
        S = Pos(p, 1.0)
        r = dict(code=l["code"], day=l["day"], hold=hold, net=l["net"], mint=l["mint"], slot=l["slot"], idx=l["idx"], cost=l["cost"])
        c = ctx.get((l["mint"], l["slot"], l["idx"]))
        r.update(drop=c["d_drop"] if c else np.nan, dsol=c["d_sol"] if c else np.nan, ahead=c["d_nbuy"] if c and c["d_nbuy"] is not None else np.nan,
                 vsol=c["vsol"] if c else np.nan, age=c["age"] if c and c["age"] is not None else np.nan)
        for t in (400, 800):
            m = S.dcc <= t; b = m & S.bu; s_ = m & ~S.bu
            q = S.q_at(t)
            r[f"nb{t}"] = int(b.sum()); r[f"bsol{t}"] = float(S.sol[b].sum()); r[f"maxb{t}"] = float(S.sol[b].max()) if b.any() else 0.0
            r[f"nbw{t}"] = len(set(p["us"][b].tolist())); r[f"nfol{t}"] = len(set(p["us"][b].tolist()) & FOL[l["day"]]); r[f"nfb{t}"] = len(set(p["us"][b].tolist()) & fb)
            r[f"ns{t}"] = int(s_.sum()); r[f"ssol{t}"] = float(S.sol[s_].sum())
            r[f"v{t}"] = float(S.val_q(q)); r[f"vmax{t}"] = float(S.vmax[q]) if q >= 0 else float(S.v_pre)
            r[f"gap{t}"] = float(t - S.dcc[b][-1]) if b.any() else float(t)
            hm = (l["h_dcc"] > 0) & (l["h_dcc"] <= t) & l["h_bu"] & (l["h_code"] != l["code"])
            r[f"hq{t}"] = int(hm.sum())
        # P&L under several exits (our delays), and his own first-sell position
        r["pl_act"] = (float(S.val_q(l["n_before_sell"] - 1)) - 1) * S.cost
        for pol in (("MS", 400), ("MS", 800), ("MS", 1000), ("RIDE", 424, 1000, 20000), ("RIDE", 150, 300, 2000)):
            r["pl_" + "_".join(map(str, pol))] = (ev12(S, pol, DR, DT) - 1) * S.cost
        rows.append(r)
    pickle.dump(rows, open(f"{OUT}/s7_rows.pkl", "wb"))
    feats = ["nb400", "bsol400", "maxb400", "nbw400", "nfol400", "nfb400", "ns400", "ssol400", "v400", "vmax400", "gap400", "hq400",
             "nb800", "bsol800", "nbw800", "nfol800", "ns800", "ssol800", "v800", "vmax800", "gap800", "hq800", "drop", "dsol", "ahead", "vsol", "age"]
    for code in (247, 248):
        R = [r for r in rows if r["code"] == code]
        fast = [r for r in R if r["hold"] < 1000]; mid = [r for r in R if 1000 <= r["hold"] < 2000]; slow = [r for r in R if 4000 <= r["hold"] < 8000]
        P(f"\n## bot {code}: fast (< 1 s) {len(fast):,} lots {1000 * np.mean([r['net'] for r in fast]):+.1f} mSOL/lot | 1-2 s {len(mid):,} {1000 * np.mean([r['net'] for r in mid]):+.1f} | 4-8 s {len(slow):,} {1000 * np.mean([r['net'] for r in slow]):+.1f}")
        P("| feature (window after his buy) | < 1 s mean | 1-2 s mean | 4-8 s mean | < 1 s median | 4-8 s median |"); P("|---|---|---|---|---|---|")
        for f in feats:
            a = np.array([r[f] for r in fast], float); b_ = np.array([r[f] for r in mid], float); c = np.array([r[f] for r in slow], float)
            P(f"| {f} | {np.nanmean(a):.3f} | {np.nanmean(b_):.3f} | {np.nanmean(c):.3f} | {np.nanmedian(a):.3f} | {np.nanmedian(c):.3f} |")
        P(f"\n### bot {code}: P&L per group under other exits (curve mSOL/lot, our measured delays; ACT = his own first-sell position, replayed)")
        P("| group | lots | realized | ACT | MS400 | MS800 | MS1000 | RIDE(424,1000,20000) | RIDE(150,300,2000) |"); P("|---|---|---|---|---|---|---|---|---|")
        for name, G in (("< 1 s", fast), ("1-2 s", mid), ("2-4 s", [r for r in R if 2000 <= r["hold"] < 4000]), ("4-8 s", slow),
                        ("8-15 s", [r for r in R if 8000 <= r["hold"] < 15000]), ("all", R)):
            P(f"| {name} | {len(G):,} | " + " | ".join(f"{1000 * np.mean([r[k] for r in G]):+.1f}" for k in ("net", "pl_act", "pl_MS_400", "pl_MS_800", "pl_MS_1000", "pl_RIDE_424_1000_20000", "pl_RIDE_150_300_2000")) + " |")
        # walk-forward GBDT: fast (<2 s) vs slow (4-8 s), features at 400 ms only (+ entry context)
        try:
            from sklearn.ensemble import HistGradientBoostingClassifier
            from sklearn.metrics import roc_auc_score
            f4 = [f for f in feats if f.endswith("400")] + ["drop", "dsol", "ahead", "vsol", "age"]
            S_ = [r for r in R if r["hold"] < 2000 or 4000 <= r["hold"] < 8000]
            Xm = np.array([[r[f] for f in f4] for r in S_], float); y = np.array([r["hold"] < 2000 for r in S_]); dd = np.array([r["day"] for r in S_])
            P(f"\n### bot {code}: walk-forward GBDT, '< 2 s' vs '4-8 s', features at 400 ms + entry context")
            P("| test day | n | AUC | AUC with v400 only |"); P("|---|---|---|---|")
            for d in range(2, 7):
                tr = dd < d; te = dd == d
                if te.sum() < 50 or len(set(y[te])) < 2: continue
                m = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15).fit(Xm[tr], y[tr])
                auc = roc_auc_score(y[te], m.predict_proba(Xm[te])[:, 1])
                auc1 = roc_auc_score(y[te], Xm[te][:, f4.index("v400")])
                P(f"| D{d} | {te.sum():,} | {auc:.3f} | {auc1:.3f} |")
        except Exception as e:
            P(f"(GBDT skipped: {e})")
    open(f"{OUT}/s7.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
