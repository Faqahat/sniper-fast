"""FOLLOW shared helpers: labels from the f2 crossing values, a numpy histogram GBDT (squared loss; adapted from ops/select/e_model.py),
the armed-window replay (token level, draws, blocking, concurrency cap), costs, today's pre-send baseline windows."""
import sys, json, pickle, collections, heapq
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/follow"
SMS = 212.0
PF = 0.52            # MEASURED (f2b): live fill 0.439 vs model 0.841 on 2,097 live windows that saw a crossing -> fill thinning
FILL_NOW = 2.01e-3   # MEASURED (exec D): pre-send fill tx 0.205 + sell 1.805 mSOL
FILL_S2 = 0.49e-3    # exec D recipe S2: fill 0.205 + his sell recipe ~0.28 mSOL
TRY = 5.12e-6        # MEASURED failed try (5,120 lamports)
CAL_A, CAL_B = 0.61, -1.17e-3   # DV8 calibration live = 0.61 x model - 1.17 mSOL per fill (borrowed from regular fires)
BLOCK_MS = 1400.0    # after a fill: wave exit <= 1 s + sell landing ~60 ms + the engine's 300 ms margin
NB = 34


# ---------------- GBDT (squared loss)
def binize(X, tr):
    B = np.zeros(X.shape, np.uint8); edges = []
    for j in range(X.shape[1]):
        x = X[:, j]; xt = x[tr & ~np.isnan(x)]
        e = np.unique(np.quantile(xt, np.linspace(0, 1, 33)[1:-1])) if len(xt) else np.array([])
        edges.append(e); b = np.searchsorted(e, x, side="right") + 1; b[np.isnan(x)] = 0; B[:, j] = b
    return B, edges


def apply_bins(X, edges):
    B = np.zeros(X.shape, np.uint8)
    for j, e in enumerate(edges):
        b = np.searchsorted(e, X[:, j], side="right") + 1; b[np.isnan(X[:, j])] = 0; B[:, j] = b
    return B


def build(Bm, gr, rows, depth, lam=50.0, min_n=200):
    G = gr[rows].sum(); H = float(len(rows))
    if depth == 0 or len(rows) < 2 * min_n: return {"w": -G / (H + lam)}
    F = Bm.shape[1]
    flat = (Bm[rows].astype(np.int64) + NB * np.arange(F)).ravel()
    hg = np.bincount(flat, np.repeat(gr[rows], F), NB * F).reshape(F, NB)
    hn = np.bincount(flat, None, NB * F).reshape(F, NB)
    cg, cn = hg.cumsum(1), hn.cumsum(1)
    gain = cg ** 2 / (cn + lam) + (G - cg) ** 2 / (H - cn + lam) - G ** 2 / (H + lam)
    gain[(cn < min_n) | (H - cn < min_n)] = -1; gain[:, -1] = -1
    j, b = np.unravel_index(np.argmax(gain), gain.shape)
    if gain[j, b] <= 0: return {"w": -G / (H + lam)}
    left = rows[Bm[rows, j] <= b]; right = rows[Bm[rows, j] > b]
    return {"f": int(j), "b": int(b), "gain": float(gain[j, b]), "l": build(Bm, gr, left, depth - 1, lam, min_n), "r": build(Bm, gr, right, depth - 1, lam, min_n)}


def pred(t, Bm):
    out = np.zeros(len(Bm)); stack = [(t, np.arange(len(Bm)))]
    while stack:
        n, ix = stack.pop()
        if "w" in n: out[ix] = n["w"]; continue
        m = Bm[ix, n["f"]] <= n["b"]; stack.append((n["l"], ix[m])); stack.append((n["r"], ix[~m]))
    return out


def imp(t, acc):
    if "w" in t: return
    acc[t["f"]] += t["gain"]; imp(t["l"], acc); imp(t["r"], acc)


def fit(Bm, y, tr, va, rounds=250, lr=0.08, depth=3, sub=0.35, seed=0):
    rng = np.random.default_rng(seed); f0 = float(y[tr].mean()); f = np.full(len(y), f0); trees = []; best = (1e18, 0)
    trn = np.flatnonzero(tr)
    for k in range(rounds):
        gr = f - y
        rows = rng.choice(trn, int(len(trn) * sub), replace=False)
        t = build(Bm, gr, rows, depth); f += lr * pred(t, Bm); trees.append(t)
        mse = float(np.mean((f[va] - y[va]) ** 2))
        if mse < best[0] - 1e-9: best = (mse, k + 1)
        elif k + 1 - best[1] > 40: break
    trees = trees[:best[1]]
    return dict(f0=f0, lr=lr, trees=trees)


def predict(M, Bm):
    f = np.full(len(Bm), M["f0"])
    for t in M["trees"]: f += M["lr"] * pred(t, Bm)
    return f


def importance(M, nf):
    acc = np.zeros(nf)
    for t in M["trees"]: imp(t, acc)
    return acc / max(acc.sum(), 1e-12)


def auc(y, s):
    y = np.asarray(y, bool); o = np.argsort(s); r = np.empty(len(s)); r[o] = np.arange(1, len(s) + 1); p = y.sum(); n = len(y) - p
    return float((r[y].sum() - p * (p + 1) / 2) / (p * n)) if p and n else float("nan")


# ---------------- labels
def labels(labs, CV, ccr, t_c, ci, k=4, fol=0, pol=0, pf=PF):
    """per checkpoint: expected value (SOL, gross), P(fill), expected armed slots for cap index ci (window ends at the first fill)"""
    n = len(labs); V = np.zeros(n); Pf = np.zeros(n); A = np.zeros(n)
    fill = CV["fill"]; val = CV["val"]
    for i in range(n):
        S, wend = labs[i][ci]
        T0 = t_c[i]
        if not S:
            A[i] = max((wend - T0) / SMS, 1.0); continue
        S = np.asarray(S); fm = fill[S]                       # (len S, ND)
        has = fm.any(0); first = np.argmax(fm, 0)
        v = np.where(has, val[S[first], np.arange(fm.shape[1]), fol, pol], 0.0)
        tend = np.where(has, ccr[S[first]], wend)
        V[i] = pf * v.mean(); Pf[i] = pf * has.mean()
        A[i] = max((pf * (tend - T0).mean() + (1 - pf) * (wend - T0)) / SMS, 1.0)
    return V, Pf, A


def net(V, Pf, A, k=4, fillc=FILL_NOW, cal=False):
    g = (CAL_A * V + CAL_B * Pf) if cal else V
    return g - Pf * fillc - A * k * TRY


# ---------------- today's pre-send (T2) windows on a mint, for the overlap test
def baseline_windows(R, X, a, b, info_m):
    """[start cc, end cc] of today's pre-send windows (presend.rs T2: a non-creator, non-create-slot wallet whose FIRST >= 3 % buy
    leaves it >= 5 %, curve < 100 SOL; window from +50 ms to the end of trigger slot + 10, or the whale's next sell + 30 ms).
    QUIET skip/stop and one-window-per-token are ignored (more overlap = conservative for the added value)."""
    us = R["user"][a:b].astype(np.int64); bu = R["buy"][a:b].astype(bool); sl = R["slot"][a:b].astype(np.int64)
    bb = X["bb"][a:b]; ba = X["ba"][a:b]; cc = X["cc"][a:b]; vs = R["vsol"][a:b]
    cs = info_m["cs"]; cr = info_m["creator"]
    csb = set(us[(sl == cs) & bu].tolist()) if cs is not None else set()
    seen = set(); W = []
    for r in np.flatnonzero(bu & (bb < 3e13) & (ba >= 3e13) & (vs < 100e9)).tolist():
        u = int(us[r])
        if u in seen: continue
        seen.add(u)
        if u == cr or u in csb or ba[r] < 5e13: continue
        nx = np.flatnonzero((us[r + 1:] == u) & ~bu[r + 1:])
        end = (sl[r] + 11) * SMS
        if len(nx): end = min(end, cc[r + 1 + nx[0]] + 30.0)
        W.append((cc[r] + 50.0, end))
    return W


# ---------------- replay
def replay(sel_rows, meta, labs, ci, CV, ccr, U, fol=0, pol=0, conc=None, want_log=False, PFJ=None):
    """sel_rows: checkpoint rows that pass the threshold (one day). Per episode the first passing checkpoint arms [t_c, wend].
    Token level: a crossing inside any live armed interval of the token, not blocked, fills when the draw fills AND the thinning
    uniform U[j, d] < PF; a fill consumes every interval live at that time and blocks the token for BLOCK_MS.
    conc = max concurrently armed TOKENS (greedy by start, token windows = merged intervals, uncut ends; extra arms dropped).
    Returns per draw: fills [(cv index, value, mint, row of the checkpoint)], armed slots; and the log of decisions."""
    first = {}
    for i in sel_rows.tolist():
        e = int(meta["e"][i])
        if e not in first or meta["t_c"][i] < meta["t_c"][first[e]]: first[e] = i
    iv = collections.defaultdict(list)
    for e, i in first.items():
        S, wend = labs[i][ci]
        iv[int(meta["m"][i])].append((float(meta["t_c"][i]), float(wend), i, S))
    dropped = set()
    if conc is not None:
        tw = []
        for m, L_ in iv.items():
            L_.sort()
            cur = None
            for s, e_, i, S in L_:
                if cur and s <= cur[1]: cur[1] = max(cur[1], e_); cur[2].append(i)
                else:
                    if cur: tw.append(cur)
                    cur = [s, e_, [i], m]
            if cur: tw.append(cur)
        tw.sort(key=lambda z: z[0]); h = []
        for s, e_, ii, m in tw:
            while h and h[0] <= s: heapq.heappop(h)
            if len(h) >= conc: dropped.update(ii); continue
            heapq.heappush(h, e_)
    ND = CV["fill"].shape[1]
    fills = [[] for _ in range(ND)]; armed = collections.defaultdict(lambda: np.zeros(ND)); log = []
    for m, L_ in iv.items():
        L_ = [z for z in L_ if z[2] not in dropped]
        if not L_: continue
        cvs = sorted({j for z in L_ for j in z[3]}, key=lambda j: ccr[j])
        for d in range(ND):
            ends = {z[2]: z[1] for z in L_}; blocked = -1e18; fl = []
            for j in cvs:
                cj = ccr[j]
                if cj <= blocked: continue
                act = [z for z in L_ if z[0] < cj <= ends[z[2]]]
                if not act: continue
                ok = bool(CV["fill"][j, d]) and U[j, d] < (PF if PFJ is None else PFJ[j, d])
                if want_log and d == 0: log.append(("try", j, [z[2] for z in act], ok, m))
                if not ok: continue
                v = float(CV["val"][j, d, fol, pol])
                fills[d].append((j, v, m, act[0][2])); fl.append(j)
                for z in act: ends[z[2]] = cj
                blocked = cj + BLOCK_MS
            # armed time = union of [start, (cut) end]
            segs = sorted((z[0], ends[z[2]]) for z in L_)
            tot = 0.0; cs_, ce_ = None, None
            for s, e_ in segs:
                if e_ <= s: e_ = s + SMS
                if cs_ is None: cs_, ce_ = s, e_
                elif s <= ce_: ce_ = max(ce_, e_)
                else: tot += ce_ - cs_; cs_, ce_ = s, e_
            if cs_ is not None: tot += ce_ - cs_
            armed[m][d] += tot / SMS
    return fills, armed, first, iv, dropped, log
