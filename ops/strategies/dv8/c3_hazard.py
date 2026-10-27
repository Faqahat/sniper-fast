#!/usr/bin/env python3
"""DV8 step 2c (read-only): a contention-aware landing model = where in the chain order after the dump our buy lands.
Discrete hazard: walking the outside trades after the dump in chain order, P(our buy lands before trade x | not yet) =
logistic(features of x): cc delay of x after the dump (bins), x in the dump slot, x is a buy, x's wallet speed class
(median cc delay of the wallet's buys within 3 slots after >=5% dumps on D0-D1 = 10-22/10-23, before any live run: fast <25 ms,
mid 25-80, slow >80, unknown). Fitted on live regular fires (MEASURED positions), scored on held-out halves like c2.
Out: dv8/c3.txt, dv8/hazard.json, dv8/wspeed.npy (wallet id -> class)"""
import json, pickle, collections, sys, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L, dv8sim as S
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
DB = (0, 5, 15, 30, 60, 120, 250, 1e9)
NF = (len(DB) - 1) + 1 + 1 + 4      # delay bins, same slot, buy, speed class one-hot (4)


def wallet_speed():
    """median cc delay of each wallet's buys within 3 slots after an outside >=5% sell >=0.5 SOL, D0-D1 (pre-live)"""
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    t1 = L.DAY0 + 2 * 86400
    n = int(np.searchsorted(np.asarray(T["bt"][::1000]), t1)) * 1000      # bt ~monotone
    X = np.asarray(T[:n]); X = X[X["bt"] < t1]
    X = X[np.lexsort((X["j"], X["idx"], X["slot"], X["mint"]))]
    sl = X["slot"].astype(np.int64); cc = L.cc(sl, X["idx"]); mi = X["mint"]
    px = X["vsol"] / np.maximum(X["vtok"].astype(np.float64), 1)
    same = np.r_[False, mi[1:] == mi[:-1]]
    pprev = np.r_[np.nan, px[:-1]]
    drop = np.where(same & (X["buy"] == 0), 1 - px / pprev, 0)
    dumps = np.flatnonzero((drop >= 0.05) & (X["sol"] >= 5e8))
    dl = collections.defaultdict(list)
    for j in dumps:
        k = j + 1
        while k < len(X) and mi[k] == mi[j] and sl[k] <= sl[j] + 3:
            if X["buy"][k]: dl[int(X["user"][k])].append(cc[k] - cc[j])
            k += 1
    sp = {u: (np.median(v), len(v)) for u, v in dl.items() if len(v) >= 5}
    return sp


def feats(R, jd, k_max, wsp):
    sl = R["slot"].astype(np.int64); c = L.cc(sl, R["idx"])
    rows = []
    for x in range(jd + 1, min(jd + 1 + k_max, len(R))):
        f = np.zeros(NF)
        d = c[x] - c[jd]; f[int(np.searchsorted(DB, d, side="right") - 1)] = 1
        f[len(DB) - 1] = float(sl[x] == sl[jd]); f[len(DB)] = float(R["buy"][x])
        f[len(DB) + 1 + wsp.get(int(R["user"][x]), 3)] = 1
        rows.append(f)
    return np.array(rows).reshape(-1, NF)


def logit_fit(X, y, l2=1.0, it=50):
    w = np.zeros(X.shape[1])
    for _ in range(it):
        p = 1 / (1 + np.exp(-X @ w)); g = X.T @ (p - y) + l2 * w
        H = (X * (p * (1 - p))[:, None]).T @ X + l2 * np.eye(len(w))
        w -= np.linalg.solve(H, g)
    return w


def main():
    t0 = time.time()
    sp = wallet_speed()
    wsp = {u: (0 if m < 25 else (1 if m < 80 else 2)) for u, (m, n) in sp.items()}
    P(f"# Hazard landing model; wallet speed classes from D0-D1: fast {sum(v == 0 for v in wsp.values())}, mid {sum(v == 1 for v in wsp.values())}, slow {sum(v == 2 for v in wsp.values())} ({time.time() - t0:.0f}s)")
    json.dump({str(k): v for k, v in wsp.items()}, open(f"{L.D}/wspeed.json", "w"))
    F = pickle.load(open(f"{L.D}/fires_tape.pkl", "rb"))
    ids, idm = L.ids_map()
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    mids = np.array(sorted({idm[f["mint"]] for f in F if f["mint"] in idm}), np.uint32)
    TT = np.asarray(T[np.isin(T["mint"], mids)])
    TT = TT[np.lexsort((TT["j"], TT["idx"], TT["slot"], TT["mint"]))]
    um, st = np.unique(TT["mint"], return_index=True); en = np.append(st[1:], len(TT))
    span = {ids[int(m)]: (int(a), int(b)) for m, a, b in zip(um, st, en)}
    wid = [idm[w] for w in L.WAL.values()]
    rows = pickle.load(open(f"{L.D}/c1_rows.pkl", "rb")); live_pnl = {(r["run"], r["t"]): r.get("realized", 0.0) for r in rows}
    C = []
    for f in F:
        if f["us"] is None or f["ds"] is None or f["mint"] not in span: continue
        a, b = span[f["mint"]]; R = TT[a:b]; R = R[~np.isin(R["user"], wid)]
        key = R["slot"].astype(np.int64) * 100000 + R["idx"].astype(np.int64)
        jd = np.flatnonzero(key == f["ds"] * 100000 + f["di"])
        if not len(jd): continue
        jd = int(jd[-1]); k = int(np.searchsorted(key, f["us"][0] * 100000 + f["us"][1])) - jd - 1
        X = feats(R, jd, 40, wsp)
        C.append(dict(f=f, R=R, jd=jd, k=k, X=X, live=live_pnl.get((f["run"], f["t"]), 0.0)))
    P(f"fires {len(C)}; trades-ahead composition (MEASURED): share of trades ahead of us by wallet class fast/mid/slow/unknown = " +
      " / ".join(f"{100 * np.mean([c['X'][i, len(DB) + 1 + s] for c in C for i in range(min(c['k'], len(c['X'])))]):.0f}%" for s in range(4)))
    P("share of the trades right BEHIND us (next 3) by class fast/mid/slow/unknown = " +
      " / ".join(f"{100 * np.mean([c['X'][i, len(DB) + 1 + s] for c in C for i in range(c['k'], min(c['k'] + 3, len(c['X'])))]):.0f}%" for s in range(4)))

    def design(cs):
        Xs, ys = [], []
        for c in cs:
            m = min(c["k"] + 1, len(c["X"]))
            if m == 0: continue
            Xs.append(c["X"][:m]); y = np.zeros(m); 
            if c["k"] < len(c["X"]): y[c["k"]] = 1     # stop before trade k (= we land before it)
            ys.append(y)
        return np.vstack(Xs), np.concatenate(ys)

    rng = np.random.default_rng(4)

    def draw_k(c, w, n=40):
        p = 1 / (1 + np.exp(-c["X"] @ w)) if len(c["X"]) else np.zeros(0)
        ks = []
        for _ in range(n):
            u = rng.random(len(p)); hit = np.flatnonzero(u < p)
            ks.append(int(hit[0]) if len(hit) else len(p))
        return ks

    def score(cs, w):
        res = []
        for c in cs:
            f = c["f"]; R = c["R"]; jd = c["jd"]; n = len(R); sl = R["slot"].astype(np.int64)
            vs = R["vsol"] / 1e9; vt = R["vtok"].astype(np.float64); sol = R["sol"] / 1e9; tk = R["tok"].astype(np.float64); bu = R["buy"].astype(bool)
            size = f["spend"]; hold = f["hold"] or 5; tokd = S.entry_tokens(vs[jd], vt[jd], size)
            fl, pn = [], []
            for k in draw_k(c, w):
                r = jd + 1 + k
                if r > n - 1: fl.append(True); pn.append(0.0); continue
                es = int(sl[r - 1]) if k > 0 else int(sl[jd])
                ok = S.entry_tokens(vs[r - 1], vt[r - 1], size) >= tokd / 1.05; fl.append(ok)
                if ok and sl[-1] >= es + hold:
                    qt = int(np.searchsorted(sl, es + hold, side="right")) - 1
                    pn.append(S.pnl_exact(vs, vt, sol, tk, bu, r, qt, size))
                else: pn.append(0.0)
            res.append((np.mean(fl), np.mean(pn), np.mean([min(k, 40) for k in draw_k(c, w, 10)])))
        return np.array(res)

    P("\n| test set | n | live fill % | hazard fill % | live k mean | hazard k mean | live mSOL/fire | hazard mSOL/fire |"); P("|---|---|---|---|---|---|---|---|")
    mid = np.median([c["f"]["t"] for c in C])
    for nm, sel in (("AMS (fit FRA)", lambda c: c["f"]["srv"] == "AMS"), ("FRA (fit AMS)", lambda c: c["f"]["srv"] == "FRA"),
                    ("late half (fit early)", lambda c: c["f"]["t"] >= mid), ("early half (fit late)", lambda c: c["f"]["t"] < mid)):
        te = [c for c in C if sel(c)]; tr = [c for c in C if not sel(c)]
        X, y = design(tr); w = logit_fit(X, y)
        s = score(te, w)
        P(f"| {nm} | {len(te)} | {100 * np.mean([c['f']['out'] == 'fill' for c in te]):.0f} | {100 * s[:, 0].mean():.0f} | {np.mean([c['k'] for c in te]):.2f} | {s[:, 2].mean():.2f} | "
          f"{1000 * np.mean([c['live'] for c in te]):+.2f} | {1000 * s[:, 1].mean():+.2f} |")
    X, y = design(C); w = logit_fit(X, y)
    s = score(C, w); lp = np.array([c["live"] for c in C])
    P(f"| ALL (in-sample) | {len(C)} | {100 * np.mean([c['f']['out'] == 'fill' for c in C]):.0f} | {100 * s[:, 0].mean():.0f} | {np.mean([c['k'] for c in C]):.2f} | {s[:, 2].mean():.2f} | {1000 * lp.mean():+.2f} | {1000 * s[:, 1].mean():+.2f} |")
    g = np.random.default_rng(1); bs = [1000 * (lp[ii].mean() - s[ii, 1].mean()) for ii in (g.integers(0, len(C), len(C)) for _ in range(2000))]
    P(f"- live - hazard: {1000 * (lp.mean() - s[:, 1].mean()):+.2f} mSOL/fire [5-95%: {np.percentile(bs, 5):+.2f} .. {np.percentile(bs, 95):+.2f}]")
    names = [f"d{DB[i]}-{DB[i + 1]}" for i in range(len(DB) - 1)] + ["same_slot", "buy", "w_fast", "w_mid", "w_slow", "w_unknown"]
    P("hazard weights (log-odds that we land BEFORE trade x): " + ", ".join(f"{n} {v:+.2f}" for n, v in zip(names, w)))
    json.dump(dict(DB=list(DB), w=list(w), names=names), open(f"{L.D}/hazard.json", "w"))
    open(f"{L.D}/c3.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
