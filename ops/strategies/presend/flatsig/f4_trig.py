#!/usr/bin/env python3
"""FLATSIG step 4 [MEASURED features, causal]: every T2-like trigger on the recorded chain (a landed buy of >= 6% of supply on the
bonding curve) and every trigger of OUR live positions (T2 whale buy / re-arm dump, matched by mint+slot+idx) ->
  features from rows STRICTLY BEFORE the trigger row (chain order slot, idx, j) or global state with time < trigger,
  labels from rows AFTER it (bots' entries, the 12% dip, its paper fill).
Bot sets: NAMED (flib), plus COH = the data-driven cohort written by f5_cohort.py (if present; DEV-only fit).
Out: /home/moiz/sniper-data/flatsig/trig.pkl  {"cols": [...], "X": float array, "meta": list of dicts}"""
import numpy as np, pickle, json, collections, sys, os, bisect
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flib as L

D = L.D
SUP = 1e15
K = 30e9 * 1.073e15            # pump curve constant product (vsol * vtok); price ~ vsol^2 / K
W_LAB = 12                     # label window: slots after the trigger
DIP = 0.12

z = np.load(f"{D}/chain.npz")
S, I, J, M, U, B = z["slot"], z["idx"], z["j"], z["mint"], z["user"], z["buy"]
SOL, TOK, VS, BT = z["sol"].astype(np.float64), z["tok"].astype(np.float64), z["vsol"].astype(np.float64), z["bt"]
n = len(S)
print("rows", n, flush=True)
fz = np.load(f"{D}/fails.npz")
FS, FI, FP, FM, FK = fz["slot"], fz["idx"], fz["payer"], fz["mint"], fz["kind"]
spans = json.load(open(f"{D}/spans.json"))

COH = set()
if os.path.exists(f"{D}/cohort.json"):
    COH = {int(x) for x in json.load(open(f"{D}/cohort.json"))["ids"]}
named = np.array(sorted(L.NAMED64), dtype=np.uint64)
coh = np.array(sorted(COH), dtype=np.uint64)
isN = np.isin(U, named)
isC = np.isin(U, coh) if len(coh) else np.zeros(n, bool)
core = np.array(sorted(k for k, v in L.NAMED64.items() if v in L.CORE3), dtype=np.uint64)
isK = np.isin(U, core)
fN = np.isin(FP, named); fC = np.isin(FP, coh) if len(coh) else np.zeros(len(FP), bool)

# mint groups
mstart = np.r_[0, np.nonzero(M[1:] != M[:-1])[0] + 1]
mend = np.r_[mstart[1:], n]
gid = np.repeat(np.arange(len(mstart)), mend - mstart)
# failed rows per mint
fms = {}
if len(FM):
    fs0 = np.r_[0, np.nonzero(FM[1:] != FM[:-1])[0] + 1]; fe0 = np.r_[fs0[1:], len(FM)]
    for a, b in zip(fs0, fe0): fms[int(FM[a])] = (a, b)

# global time-ordered named / cohort bot buys (regime gauge): slot arrays
gN = np.sort(S[isN & (B == 1)]); gC = np.sort(S[isC & (B == 1)]) if isC.any() else np.array([], np.int64)
gAll = np.sort(S[B == 1])

def in_span(s):
    for _, lo, hi in spans:
        if lo + 300 <= s <= hi - 30: return True
    return False

def span_lo(s):
    for _, lo, hi in spans:
        if lo <= s <= hi: return lo
    return None

# ---------- which rows are triggers ----------
cand = np.nonzero((B == 1) & (TOK >= 0.06 * SUP) & (VS > 0))[0]
want = {}     # row -> list of our positions
P = L.all_positions()
rowkey = {}
for p in P:
    if p["trig_slot"] is None: continue
    rowkey.setdefault((L.pk64(p["mint"]), p["trig_slot"], p["trig_idx"]), []).append(p["id"])
# find rows of our triggers
ourrows = {}
if rowkey:
    km = np.array([k[0] for k in rowkey], dtype=np.uint64)
    for (m, s, i), ids in rowkey.items():
        g = np.searchsorted(M, np.uint64(m))
        if g >= n or M[g] != m: continue
        e = np.searchsorted(M, np.uint64(m), side="right")
        ss = S[g:e]; ii = I[g:e]
        hit = np.nonzero((ss == s) & (ii == i))[0]
        if len(hit): ourrows[g + int(hit[0])] = ids
rows = sorted(set(cand.tolist()) | set(ourrows))
print("candidate T2 rows", len(cand), "our matched", len(ourrows), "of", len(rowkey), flush=True)

# whale / creator histories need time order
rows_t = sorted(rows, key=lambda r: (S[r], I[r]))
wh_hist = collections.defaultdict(list)    # whale -> [(slot, botsN, botsC, dipfilled)]
cr_hist = collections.defaultdict(list)    # creator -> [(slot, botsN)]
creator_of = {}

cols = ["age", "age_cens", "vsol_pre", "pct", "sol", "n_prior", "n_60", "n_120", "n_10s", "buyers", "sellers", "buy_sol_60",
        "sell_sol_60", "nN_prior", "nN_dist", "nN_50", "nN_hold", "nN_last_age", "nC_prior", "nC_dist", "nC_50", "nC_hold",
        "fN_prior", "fC_prior", "wh_n", "wh_botN", "wh_botC", "wh_prev_age", "cr_n", "cr_botN", "cr_is_whale", "hour",
        "gN_300", "gC_300", "gAll_300", "gN_3600", "nb_same_slot", "big_sells_60", "max_hold_pct"]
X = []; meta = []
for k, r in enumerate(rows_t):
    g = gid[r]; a = mstart[g]; s = int(S[r]); bt = int(BT[r]); m = int(M[r]); wh = int(U[r])
    pr = slice(a, r)
    ps, pb, pu, psol, ptok, pbt = S[pr], B[pr], U[pr], SOL[pr], TOK[pr], BT[pr]
    first_s = int(S[a]); lo = span_lo(s)
    age = s - first_s; cens = 1.0 if (lo is None or first_s <= lo + 2) else 0.0
    vpre = VS[r] - SOL[r]
    creator = creator_of.get(m)
    if creator is None:
        creator = int(U[a]) if not cens else 0
        creator_of[m] = creator
    # flow
    m60 = pbt >= bt - 60; m120 = pbt >= bt - 120; m10 = pbt >= bt - 10
    nN = isN[pr]; nC = isC[pr]
    # holdings (token units) of named / cohort before trigger
    sgn = np.where(pb == 1, ptok, -ptok)
    def hold(mask):
        if not mask.any(): return 0
        uu, inv = np.unique(pu[mask], return_inverse=True)
        return int((np.bincount(inv, weights=sgn[mask]) > 1e9).sum())
    if len(pu):
        uu, inv = np.unique(pu, return_inverse=True); maxh = float(np.bincount(inv, weights=sgn).max()) / SUP * 100
    else: maxh = 0.0
    fa = fms.get(m)
    fpr = (0, 0)
    if fa:
        fsl = FS[fa[0]:fa[1]]; fin = FI[fa[0]:fa[1]]
        pre = (fsl < s) | ((fsl == s) & (fin < I[r]))
        fpr = (int((fN[fa[0]:fa[1]] & pre).sum()), int((fC[fa[0]:fa[1]] & pre).sum()))
    # whale / creator history (only past triggers whose label window closed)
    wl = [x for x in wh_hist[wh] if x[0] + W_LAB < s]
    cl = [x for x in cr_hist[creator] if x[0] + W_LAB < s] if creator else []
    nNlast = int(s - ps[nN].max()) if nN.any() else 99999
    x = [age, cens, vpre / 1e9, TOK[r] / SUP * 100, SOL[r] / 1e9, r - a, int(m60.sum()), int(m120.sum()), int(m10.sum()),
         len(set(pu[pb == 1].tolist())), len(set(pu[pb == 0].tolist())), psol[m60 & (pb == 1)].sum() / 1e9, psol[m60 & (pb == 0)].sum() / 1e9,
         int(nN.sum()), len(set(pu[nN].tolist())), int((nN & (ps >= s - 50)).sum()), hold(nN), nNlast,
         int(nC.sum()), len(set(pu[nC].tolist())), int((nC & (ps >= s - 50)).sum()), hold(nC), fpr[0], fpr[1],
         len(wl), sum(1 for x_ in wl if x_[1]) / len(wl) if wl else -1, sum(1 for x_ in wl if x_[2]) / len(wl) if wl else -1,
         (s - wl[-1][0]) if wl else 99999, len(cl), sum(1 for x_ in cl if x_[1]) / len(cl) if cl else -1,
         1.0 if creator == wh else 0.0, ((bt + 5 * 3600) % 86400) / 3600.0,
         int(np.searchsorted(gN, s) - np.searchsorted(gN, s - 750)), int(np.searchsorted(gC, s) - np.searchsorted(gC, s - 750)) if len(gC) else 0,
         int(np.searchsorted(gAll, s) - np.searchsorted(gAll, s - 750)), int(np.searchsorted(gN, s) - np.searchsorted(gN, s - 9000)),
         int(((ps == s)).sum()), int((m60 & (pb == 0) & (psol >= 1e9)).sum()), maxh]
    # ---- labels (after the trigger) ----
    e = mend[g]
    post = slice(r + 1, e)
    qs, qb, qu, qv = S[post], B[post], U[post], VS[post]
    wmask = qs <= s + W_LAB
    lN = int((isN[post] & (qb == 1) & wmask).sum()); lC = int((isC[post] & (qb == 1) & wmask).sum()); lK = int((isK[post] & (qb == 1) & wmask).sum())
    namesN = sorted({L.NAMED64[int(u_)] for u_ in qu[isN[post] & (qb == 1) & wmask]})
    fpost = (0, 0)
    if fa:
        fsl = FS[fa[0]:fa[1]]; fin = FI[fa[0]:fa[1]]; fk = FK[fa[0]:fa[1]]
        po = ((fsl > s) | ((fsl == s) & (fin > I[r]))) & (fsl <= s + W_LAB) & (fk == 1)
        fpost = (int((fN[fa[0]:fa[1]] & po).sum()), int((fC[fa[0]:fa[1]] & po).sum()))
    # 12% dip within 10 slots (price ~ vsol^2): first row where vsol <= sqrt(0.88) * vsol_post_trigger
    vth = VS[r] * np.sqrt(1 - DIP)
    dm = np.nonzero((qs <= s + 10) & (qv <= vth) & (qv > 0))[0]
    dip_row = r + 1 + int(dm[0]) if len(dm) else None
    dlab = {}
    if dip_row is not None:
        ds = int(S[dip_row])
        after = slice(dip_row + 1, e)
        aS, aB = S[after], B[after]
        for wv in (0, 1, 2, 5):
            mm = (aS <= ds + wv) & (aB == 1)
            dlab[f"dN{wv}"] = int((isN[after] & mm).sum()); dlab[f"dC{wv}"] = int((isC[after] & mm).sum())
            dlab[f"dAll{wv}"] = int(mm.sum())
            dlab[f"dSol{wv}"] = float(SOL[after][mm].sum() / 1e9)
        dlab["dip_slot"] = ds; dlab["dip_seller"] = int(U[dip_row]); dlab["dip_sol"] = float(SOL[dip_row] / 1e9)
    meta.append({"row": r, "mint": m, "slot": s, "bt": bt, "whale": wh, "creator": creator, "in_span": in_span(s),
                 "lN": lN, "lC": lC, "lK": lK, "fN": fpost[0], "fC": fpost[1], "namesN": namesN, "dip": dip_row is not None, **dlab,
                 "ours": ourrows.get(r, [])})
    X.append(x)
    wh_hist[wh].append((s, lN + fpost[0] > 0, lC + fpost[1] > 0, dip_row is not None))
    if creator: cr_hist[creator].append((s, lN + fpost[0] > 0))
    if k % 20000 == 0: print(k, len(rows_t), flush=True)

X = np.array(X, dtype=np.float64)
pickle.dump({"cols": cols, "X": X, "meta": meta, "coh_n": len(COH)}, open(f"{D}/trig.pkl", "wb"))
print("done", X.shape, flush=True)
