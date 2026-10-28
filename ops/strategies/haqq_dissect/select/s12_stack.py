#!/usr/bin/env python3
"""SELECT step 12 (read-only): do creator / dumper / create-tx features ADD to analyst F's tape score? (coordinator request 10-28)
Universe: F's labels (bots/labels.jsonl.gz: 1.08 M envelope sells, bought247/248 MEASURED, F's walk-forward OOS broad scores b11
score247_broad / score248_broad, D1-D6) joined on (mint, slot, idx) to my envelope (select/env.npz, which carries my features).
Per label (y247, y248, union): walk-forward stacked GBDT, test day D fitted on days 1..D-1 (F's scores on those days are themselves OOS):
  F     = logit(F247), logit(F248) only (F's ranking, recalibrated)
  F+NEW = F + creator history (CRE), seller identity/memory without haqq (sel_ncreates, sel_ntr/nmint/nsell, sel_mfol/nfol, sel_prev_env),
          create-tx (CTX), mint structure (STR), time (TIM)
  F+NEW+HQM = F+NEW + memory of haqq's own past picks (sel_prev_y/rate, cr_hq*) (still on-chain and causal)
Metrics per test day: AUC, precision at recall 10/25/50 %, rate-matched precision. VALUE (b8b method, MEASURED entries, no landing model):
for the rate-matched top-K picks of each method, every real outside buyer (not haqq, not ours) landing k = 2..7 outside trades after the dump
within slots s..s+2, return per SOL of their tokens marked (exact sell) at +2 s / +4 s; and with haqq's rows after their entry removed.
Out: select/s12.txt, s12_scores.npz"""
import sys, json, gzip, time, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/select")
import dd_gbdt as G
import dv8lib as L
from s4_wf import load, CRE, SEL, STR, TIM, HQMEM
OUT = "/home/moiz/sniper-data/haqq_dissect/select"
RNEG = 0.15


def auc(s, y):
    o = np.argsort(s, kind="stable"); r = np.empty(len(s)); r[o] = np.arange(1, len(s) + 1)
    n1 = y.sum(); n0 = len(y) - n1
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / max(n1 * n0, 1))


def prec_at_recall(s, y, rec):
    o = np.argsort(-s); yy = y[o]; cp = np.cumsum(yy); k = int(np.searchsorted(cp, rec * yy.sum())) + 1
    return float(cp[k - 1] / k)


def lg(p):
    p = np.clip(p, 1e-6, 1 - 1e-6); return np.log(p / (1 - p))


def values(ev, ids_, idm):
    """b8b proxy for events [(env_index, mint, slot, idx)] -> dict env_index -> list of (k, r2, r4, r2x, r4x)"""
    our = [idm[w] for w in L.WAL.values() if w in idm]; H = idm[L.HAQQ]
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    mints = np.unique(np.array([e[1] for e in ev], np.uint32))
    sel = np.isin(np.asarray(T["mint"]), mints) & ~np.isin(np.asarray(T["user"]), our)
    cols = ("slot", "idx", "mint", "user", "buy", "sol", "tok", "vsol", "vtok", "fee_bps", "cfee_bps")
    S = np.zeros(int(sel.sum()), dtype=[(c, T.dtype[c]) for c in cols])
    for c in cols: S[c] = np.asarray(T[c])[sel]
    S = S[np.lexsort((S["idx"], S["slot"], S["mint"]))]
    um, st = np.unique(S["mint"], return_index=True); en = np.append(st[1:], len(S)); span = {int(m): (int(a), int(b)) for m, a, b in zip(um, st, en)}
    cc_all = L.cc(S["slot"].astype(np.int64), S["idx"].astype(np.int64))
    res = {}
    for u, m, s0, i0 in ev:
        a, b = span[int(m)]; X = S[a:b]; cc = cc_all[a:b]
        sl = X["slot"].astype(np.int64); ix = X["idx"].astype(np.int64)
        jd = np.flatnonzero((sl == s0) & (ix == i0) & (X["buy"] == 0))
        if not len(jd): continue
        jd = int(jd[0]); hi = int(np.searchsorted(sl, sl[jd] + 2, side="right"))
        vs = X["vsol"].astype(np.float64) / 1e9; vt = X["vtok"].astype(np.float64)
        fee = (X["fee_bps"].astype(np.float64) + X["cfee_bps"]) / 1e4; fee = np.where(fee > 0, fee, 0.0125)
        out = []
        for k, j in enumerate(range(jd + 1, min(hi, jd + 9))):
            if k < 2 or not X["buy"][j] or X["user"][j] == H: continue
            tok = float(X["tok"][j]); cost = X["sol"][j] / 1e9 * (1 + fee[j])
            if cost <= 0.01: continue
            r = []
            for dt in (2000, 4000):
                q = int(np.searchsorted(cc, cc[j] + dt, side="right")) - 1
                V, Tt = vs[q], vt[q]; r.append((V - V * Tt / (Tt + tok)) * (1 - fee[j]) / cost - 1)
            V = vs[j]; Tt = vt[j]; K = V * Tt; q4 = int(np.searchsorted(cc, cc[j] + 4000, side="right")) - 1; q2 = int(np.searchsorted(cc, cc[j] + 2000, side="right")) - 1
            r2x = None
            for rr in range(j + 1, q4 + 1):
                if X["user"][rr] != H:
                    if X["buy"][rr]: V += X["sol"][rr] / 1e9; Tt = K / V
                    else: Tt += float(X["tok"][rr]); V = K / Tt
                if rr == q2: r2x = (V - K / (Tt + tok)) * (1 - fee[j]) / cost - 1
            if r2x is None: r2x = r[0]
            out.append((k, r[0], r[1], r2x, (V - K / (Tt + tok)) * (1 - fee[j]) / cost - 1))
        res[u] = out
    return res


def main():
    t0 = time.time()
    A, ccols = load()
    ids, idm = L.ids_map()
    N = len(A["m"])
    key = {}
    em = A["m"].astype(np.int64); es = A["s"].astype(np.int64); ei = A["i"].astype(np.int64)
    k_env = em * 10**13 + (es - 459000000) * 10**5 + ei
    o = np.argsort(k_env); k_sorted = k_env[o]
    F = collections.defaultdict(list)
    for line in gzip.open("/home/moiz/sniper-data/haqq_dissect/bots/labels.jsonl.gz", "rt"):
        r = json.loads(line)
        if r.get("score247_broad") is None or r.get("score248_broad") is None: continue
        m = idm.get(r["mint"])
        if m is None: continue
        F["m"].append(m); F["s"].append(r["slot"]); F["i"].append(r["idx"]); F["y247"].append(r["bought247"]); F["y248"].append(r["bought248"])
        F["f247"].append(r["score247_broad"]); F["f248"].append(r["score248_broad"])
        F["d247"].append(r["score247_dv8"] if r.get("score247_dv8") is not None else np.nan); F["d248"].append(r["score248_dv8"] if r.get("score248_dv8") is not None else np.nan)
    F = {k: np.array(v) for k, v in F.items()}
    kf = F["m"].astype(np.int64) * 10**13 + (F["s"].astype(np.int64) - 459000000) * 10**5 + F["i"].astype(np.int64)
    p = np.clip(np.searchsorted(k_sorted, kf), 0, N - 1); hit = k_sorted[p] == kf; ue = np.where(hit, o[p], -1)
    lines = []
    def P(*a):
        s = " ".join(str(x) for x in a); print(s, flush=True); lines.append(s)
    nF = len(kf)
    P(f"# F's scored sells (broad scores, D1-D6): {nF:,}; matched to my envelope {hit.sum():,} ({hit.mean():.2f}); "
      f"F positives 247 {int(F['y247'].sum()):,} (matched {int(F['y247'][hit].sum()):,}), 248 {int(F['y248'].sum()):,} (matched {int(F['y248'][hit].sum()):,}) ({time.time() - t0:.0f}s)")
    u = ue[hit]
    y247 = F["y247"][hit].astype(bool); y248 = F["y248"][hit].astype(bool)
    # sanity: my labels vs F's on the matched set
    P(f"label agreement on matched: 247 F {y247.sum():,} vs mine {int(A['y247'][u].sum()):,} (both {int((y247 & A['y247'][u]).sum()):,}); "
      f"248 F {y248.sum():,} vs mine {int(A['y248'][u].sum()):,} (both {int((y248 & A['y248'][u]).sum()):,})")
    day = A["day"][u].astype(int); mint = A["m"][u].astype(np.int64)
    base = np.column_stack([lg(F["f247"][hit]), lg(F["f248"][hit]), lg(np.nan_to_num(F["d247"][hit], nan=0.5)), lg(np.nan_to_num(F["d248"][hit], nan=0.5)),
                            np.isfinite(F["d247"][hit]).astype(float)])
    SELX = [f for f in SEL if f not in HQMEM]
    NEW = CRE + SELX + ccols + STR + TIM
    NEW = [f for f in NEW if f not in HQMEM]
    newX = np.column_stack([A["f_" + f][u].astype(np.float64) for f in NEW])
    hqX = np.column_stack([A["f_" + f][u].astype(np.float64) for f in HQMEM])
    sets = {"F": base, "F+NEW": np.hstack([base, newX]), "F+NEW+HQM": np.hstack([base, newX, hqX])}
    fnames = {"F": ["F247", "F248", "D247", "D248", "in_dv8"], "F+NEW": ["F247", "F248", "D247", "D248", "in_dv8"] + NEW}
    fnames["F+NEW+HQM"] = fnames["F+NEW"] + HQMEM
    mval = (np.random.default_rng(6).random(int(mint.max()) + 1) < 0.2)[mint]
    rng = np.random.default_rng(12)
    SC = {}
    labels = {"247": y247, "248": y248, "union": y247 | y248}
    for ln, y in labels.items():
        sub = y | (rng.random(len(y)) < RNEG)
        for nm, Xf in sets.items():
            S = np.full(len(y), np.nan); imps = np.zeros(Xf.shape[1])
            for D in range(2, 7):
                tr = sub & (day >= 1) & (day < D); fit = tr & ~mval; val = tr & mval; te = day == D
                if not te.any(): continue
                E = G.edges_of(Xf, fit, nb=32); rows = np.flatnonzero(fit | val)
                mod = G.fit(G.binize(Xf[rows], E), y[rows].astype(float), fit[rows], val[rows], loss="logistic", rounds=400, lr=0.1, depth=4, min_n=100,
                            lam=10.0, sub=0.6, fsub=0.6 if nm != "F" else 1.0, seed=D, patience=40, w=None)
                S[te] = G.predict(mod, G.binize(Xf[te], E)) + np.log(RNEG)
                imps += G.importance(mod, Xf.shape[1])
            SC[(ln, nm)] = S
            P(f"\n## label {ln}, set {nm} ({Xf.shape[1]} features) ({time.time() - t0:.0f}s)")
            P("| test day | sells | positives | AUC | prec@rec10 | prec@rec25 | prec@rec50 | rate-matched prec | raw F score: AUC / rate-matched |"); P("|---|---|---|---|---|---|---|---|---|")
            for D in range(2, 7):
                te = (day == D) & np.isfinite(S)
                if not te.any(): continue
                s = S[te]; yy = y[te]; k = int(yy.sum()); top = np.argsort(-s)[:k]
                raw = (F["f247"][hit] if ln == "247" else F["f248"][hit] if ln == "248" else np.maximum(F["f247"][hit], F["f248"][hit]))[te]
                P(f"| D{D} | {te.sum():,} | {k:,} | {auc(s, yy):.3f} | {prec_at_recall(s, yy, .1):.3f} | {prec_at_recall(s, yy, .25):.3f} | {prec_at_recall(s, yy, .5):.3f} | "
                  f"{yy[top].mean():.3f} | {auc(raw, yy):.3f} / {yy[np.argsort(-raw)[:k]].mean():.3f} |")
            if nm != "F":
                oo = np.argsort(-imps)[:12]; P("importance: " + ", ".join(f"{fnames[nm][i]} {imps[i] / imps.sum():.3f}" for i in oo))
    np.savez(f"{OUT}/s12_scores.npz", u=u, **{f"{a}|{b}": v for (a, b), v in SC.items()})
    # ---- VALUE of the rate-matched picks (b8b method), per label, F vs F+NEW, and the swapped sets
    P(f"\n# VALUE (b8b method, MEASURED real buyers k 2-7 within slots s..s+2): return per SOL marked at +2 s / +4 s; 'x' = haqq rows removed ({time.time() - t0:.0f}s)")
    picks = {}
    for ln, y in labels.items():
        for nm in ("F", "F+NEW", "F+NEW+HQM"):
            S = SC[(ln, nm)]; pk = []
            for D in range(2, 7):
                te = np.flatnonzero((day == D) & np.isfinite(S)); k = int(y[te].sum())
                pk += te[np.argsort(-S[te])[:k]].tolist()
            picks[(ln, nm)] = set(pk)
        picks[(ln, "his actual picks")] = set(np.flatnonzero(y & (day >= 2)).tolist())
    allp = sorted(set().union(*picks.values()))
    V = values([(q, int(A["m"][u[q]]), int(A["s"][u[q]]), int(A["i"][u[q]])) for q in allp], ids, idm)
    P(f"valued {len(V):,} dumps ({time.time() - t0:.0f}s)")
    P("| label | set | dumps | his-pick share | buyers k2-7 | +2 s per SOL [90%] | +4 s per SOL [90%] | +4 s haqq removed | per day +4 s (D2..D6) |"); P("|---|---|---|---|---|---|---|---|---|")
    g = np.random.default_rng(1)
    def row(ln, nm, qs, y):
        b = [(q, x) for q in qs for x in V.get(q, [])]
        if len(b) < 30: P(f"| {ln} | {nm} | {len(qs):,} | | {len(b)} | | | | |"); return
        r2 = np.array([x[1] for _, x in b]); r4 = np.array([x[2] for _, x in b]); r4x = np.array([x[4] for _, x in b]); dd = np.array([day[q] for q, _ in b])
        bs = lambda v: np.percentile([v[g.integers(0, len(v), len(v))].mean() for _ in range(500)], [5, 95])
        l2, l4 = bs(r2), bs(r4)
        P(f"| {ln} | {nm} | {len(qs):,} | {np.mean([y[q] for q in qs]):.2f} | {len(b):,} | {100 * r2.mean():+.2f}% [{100 * l2[0]:+.2f}..{100 * l2[1]:+.2f}] | "
          f"{100 * r4.mean():+.2f}% [{100 * l4[0]:+.2f}..{100 * l4[1]:+.2f}] | {100 * r4x.mean():+.2f}% | " +
          " ".join(f"{100 * r4[dd == D].mean():+.1f}" if (dd == D).sum() >= 20 else "-" for D in range(2, 7)) + " |")
    for ln, y in labels.items():
        for nm in ("his actual picks", "F", "F+NEW", "F+NEW+HQM"): row(ln, nm, sorted(picks[(ln, nm)]), y)
        a_, b_ = picks[(ln, "F")], picks[(ln, "F+NEW")]
        row(ln, "only F picks (dropped by F+NEW)", sorted(a_ - b_), y); row(ln, "only F+NEW picks (added)", sorted(b_ - a_), y)
    open(f"{OUT}/s12.txt", "w").write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
