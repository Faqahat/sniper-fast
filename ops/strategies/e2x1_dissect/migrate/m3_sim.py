#!/usr/bin/env python3
"""migrate agent, step 3: replay OUR strategy on the tape. Per (mode, size, V) and per entrable row: expected P&L for every exit
combination (over 10 stratified landing-delay samples), fill info, pool-open-sniped flag. Selection (p >= theta) is applied
later (m4) on these per-row results, so every variant shares one replay.
Modes:
  react : buy sent on seeing the crossing trade; lands d_e later (live shape, median 66 ms); +5% guard vs the crossing price;
          reverted/late buy costs FAIL_COST.
  pre   : tries armed on the crossing of V-DELTA, R tries per slot evenly spaced, first try lands d_e after the arm trade;
          a try fills when it lands while the curve is in [V, V+W] vSOL and not complete; every other landed try costs TRY_COST.
          If the window (A slots) expires before the curve reaches V, fall back to a reactive buy on the V crossing.
Exits: graduated -> sell into the pool at migration + N slots (+ d_x); on the curve -> stop (-10/-20%), predictor-drop
(continuation p120 < theta at 10/20/30/60/120 s checkpoints), timeout 30/120/600 s. A curve sell that lands after completion is
held into the pool. Out: sim_<mode>_<size>.pkl"""
import sys, pickle, json, time, numpy as np
sys.path.insert(0, "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/e2x1_migrate/pylib")
from mlib import Tape, last_before, pool_state_after, pool_fee, D, TRAIN, TEST, SLOT_S

MODE = sys.argv[1]; SIZE = float(sys.argv[2])
MED_MS = float(sys.argv[3]) if len(sys.argv) > 3 else 66.0
R = 5; DELTA = 5; W = 10; A = 47                 # pre-send: tries/slot, arm below V, fill window width, arm window (slots)
TRY_COST = 0.000005; FAIL_COST = 0.0003; RT_COST = 0.0029; GUARD = 1.05
NS = [0, 2, 5, 20, 100]; STOPS = [None, 0.10, 0.20, "pd0.3", "pd0.5"]; TOS = [30, 120, 600]
EXITS = [(n, s, to) for n in NS for s in STOPS for to in TOS]
CKS = [10, 20, 30, 60, 120]

lc = json.load(open("/home/moiz/sniper-data/dipml/livecal.json"))
d = np.array(lc["deltas"], float); d = d * (MED_MS / (np.median(d) * 212.07))
DLY = np.quantile(d, (np.arange(10) + 0.5) / 10); PAIR = [(j, (3 * j + 1) % 10) for j in range(10)]
T = Tape()
F = pickle.load(open(D + "/feat.pkl", "rb")); meta = F["meta"]; X = F["X"]; names = F["names"]
PP = pickle.load(open(D + "/feat_p.pkl", "rb"))
rows_by_mint = {}
for i, r in enumerate(meta): rows_by_mint.setdefault(r["mint"], []).append(i)
t0 = time.time()

# ---- continuation model: checkpoints after the crossing (cheap path features), label = completes within 120 s of the checkpoint
def ck_feats(rows, k, V, p0, hour):
    """features at checkpoints k + CKS seconds (None if completed / tape ended before)"""
    out = {}
    slot = rows["slot"].astype(np.int64); vs = rows["vsol"].astype(float) / 1e9; sol = rows["sol"].astype(float) / 1e9; buy = rows["buy"] == 1
    cb = np.concatenate([[0.0], np.cumsum(np.where(buy, sol, 0))]); cs = np.concatenate([[0.0], np.cumsum(np.where(buy, 0, sol))])
    cnb = np.concatenate([[0], np.cumsum(buy)])
    comp = np.nonzero(rows["rtok"] == 0)[0]; c = int(comp[0]) if len(comp) else None
    for sec in CKS:
        s2 = slot[k] + int(sec / SLOT_S); j = int(np.searchsorted(slot, s2, "right")) - 1
        if j < k or (c is not None and j >= c) or slot[-1] < s2: out[sec] = None; continue
        a10 = int(np.searchsorted(slot, s2 - 47)); a30 = int(np.searchsorted(slot, s2 - 141))
        Kk = vs[j] * (rows["vtok"][j] / 1e9); Vc = Kk / ((rows["vtok"][j] - rows["rtok"][j]) / 1e9)
        f = [V, vs[j], vs[j] / vs[k], Vc - vs[j], cb[j + 1] - cb[a10] - (cs[j + 1] - cs[a10]), cb[j + 1] - cb[a30] - (cs[j + 1] - cs[a30]),
             cnb[j + 1] - cnb[a10], cnb[j + 1] - cnb[a30], sec, p0, hour, vs[:j + 1].max() / vs[j]]
        y = (c is not None) and (slot[c] - s2) * SLOT_S <= 120
        out[sec] = (np.array(f, np.float32), float(y))
    return out

CKF = {}
hour_ix = names.index("hour")
for i, r in enumerate(meta):
    if not r["ent"] or r["edge"]: continue
    CKF[i] = ck_feats(T.trades(r["mint"]), r["k"], r["V"], float(PP["p120"][i]), float(X[i, hour_ix]))
print("checkpoint features", len(CKF), f"{time.time() - t0:.0f}s", flush=True)
from sklearn.ensemble import HistGradientBoostingClassifier
day = np.array([r["day"] for r in meta])
XX, YY = [], []
for i, d_ in CKF.items():
    if day[i] not in TRAIN: continue
    for sec, v in d_.items():
        if v is not None: XX.append(v[0]); YY.append(v[1])
cm_ = HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05, max_iter=200, min_samples_leaf=50, random_state=0).fit(np.array(XX), np.array(YY))
keys = [(i, sec) for i, d_ in CKF.items() for sec, v in d_.items() if v is not None]
pcv = cm_.predict_proba(np.array([CKF[i][sec][0] for i, sec in keys]))[:, 1]
PC = dict(zip(keys, pcv.tolist()))      # (row, sec) -> continuation p (train rows: in-sample, caveat noted in the report)
print("continuation model", len(PC), f"{time.time() - t0:.0f}s", flush=True)
del CKF

def curve_val(rows, t, xx, q, f):
    V2 = float(rows["vsol"][t]) + xx
    return (V2 - (K_ / (K_ / V2 + q))) * (1 - f) / 1e9

def sim_row(i):
    r = meta[i]; m = r["mint"]; V = r["V"]; k = r["k"]; c = r["c"]; mg = T.mig.get(m)
    rows = T.trades(m); global K_
    K_ = float(rows["vsol"][k]) * float(rows["vtok"][k]); f = (float(rows["fbps"][k]) + float(rows["cbps"][k])) / 1e4
    sk, ik = int(rows["slot"][k]), int(rows["idx"][k]); ck = T.clock(sk, ik)
    cclock = T.clock(int(rows["slot"][c]), int(rows["idx"][c])) if c is not None else np.inf
    P = T.pool_events(mg["pool"]) if mg else None; cm = T.clock(mg["slot"], mg["idx"]) if mg else None
    out = np.zeros(len(EXITS)); filled = 0.0; nfill_vs = []; tries_tot = 0.0; why = {}; gk = np.zeros(len(EXITS)); pre_hits = 0
    # arm point for pre-send
    arm_k = None
    if MODE == "pre":
        vs = rows["vsol"].astype(float) / 1e9
        # arm = first index of the run of 'vsol >= V-DELTA' that contains the crossing k
        j = k
        while j > 0 and vs[j - 1] >= V - DELTA: j -= 1
        arm_k = j if j < k else k
    for je, jx in PAIR:
        de, dx = DLY[je], DLY[jx]
        e = None; cost = 0.0; mode_used = "react"
        if MODE == "pre" and arm_k < k:
            ca = T.clock(int(rows["slot"][arm_k]), int(rows["idx"][arm_k]))
            pos = ca + de + np.arange(A * R) / R
            pos = pos[pos <= ca + A]
            ntry = 0
            for p_ in pos:
                s_, i_ = T.position(p_)
                t_ = last_before(rows, s_, i_)
                if t_ < arm_k: ntry += 1; continue
                if rows["rtok"][t_] == 0: break                     # completed: stop sending (in-flight tries revert)
                v_ = float(rows["vsol"][t_]) / 1e9
                if V <= v_ <= V + W:
                    e = t_; mode_used = "pre"; pre_hits += 1; break
                ntry += 1
            cost += (ntry + (R if e is not None else 0)) * TRY_COST
            if e is None and rows["rtok"][t_] == 0 and t_ < k:    # completed before reaching V?? (can't: k is the crossing) -> no-op
                pass
            if e is None and (pos[-1] if len(pos) else ca) < ck:     # window expired before the crossing: reactive fallback
                e = None
            elif e is None:                                          # window covered the crossing but no try fit before completion
                out -= cost; why["pre_miss"] = why.get("pre_miss", 0) + 1; tries_tot += ntry; continue
        if e is None:                                                # reactive on the crossing trade
            se, ie = T.position(ck + de)
            if (se, ie) <= (sk, ik): se, ie = sk, ik + 1
            e = max(last_before(rows, se, ie), k)
            if rows["rtok"][e] == 0:
                out -= cost + FAIL_COST; why["late"] = why.get("late", 0) + 1; continue
        Ve, Te, Re = float(rows["vsol"][e]), float(rows["vtok"][e]), float(rows["rtok"][e])
        x = SIZE * 1e9 / (1 + f); Vc = K_ / (Te - Re)
        if Ve + x >= Vc: xx = Vc - Ve; q = Re; we_complete = True
        else: xx = x; q = Te - K_ / (Ve + x); we_complete = False
        spent = xx * (1 + f) / 1e9
        if mode_used == "react":
            qd = float(rows["vtok"][k]) - K_ / (float(rows["vsol"][k]) + x)
            if (xx / q) > GUARD * (x / qd):
                out -= cost + FAIL_COST; why["guard"] = why.get("guard", 0) + 1; continue
        filled += 1; nfill_vs.append(Ve / 1e9); tries_tot += cost / TRY_COST if MODE == "pre" else 0
        ce = T.clock(int(rows["slot"][e]), int(rows["idx"][e])) if e > k else T.clock(*T.position(ck + de))
        # path after entry (our SOL stays in the curve)
        end = c if c is not None else len(rows) - 1
        lim = int(np.searchsorted(rows["slot"], int(rows["slot"][e]) + int(600 / SLOT_S) + 50, "right")) - 1
        end = min(end, max(lim, e))
        idx = np.arange(e + 1, end + 1) if end > e else np.arange(0)
        V2 = rows["vsol"][idx].astype(float) + xx
        val = (V2 - K_ / (K_ / V2 + q)) * (1 - f) / 1e9
        if len(idx):
            sl_ = rows["slot"][idx].astype(np.int64); nn = np.maximum(T.N[np.clip(sl_ - T.slo, 0, len(T.N) - 1)], 1)
            clk = sl_ + np.minimum(rows["idx"][idx] / nn, 0.999999)
        else: clk = np.zeros(0)
        def curve_exit(dec):
            sx, ix = T.position(dec + dx); t = last_before(rows, sx, ix)
            if c is not None and t >= c: return None
            if we_complete: return None
            t = max(t, e); V3 = float(rows["vsol"][t]) + xx
            return (V3 - K_ / (K_ / V3 + q)) * (1 - f) / 1e9
        grad_val = {}
        if (c is not None or we_complete) and mg is not None:
            for n in NS:
                sx, ix = T.position(cm + n + dx); kk = last_before(P, sx, ix)
                pb, pq = pool_state_after(P, kk, mg); fee = pool_fee(P, kk)
                grad_val[n] = (pq - pb * pq / (pb + q)) * (1 - fee) / 1e9
        elif we_complete:
            pb, pq = 206.9e12, 84.99e9
            for n in NS: grad_val[n] = (pq - pb * pq / (pb + q)) * (1 - 0.0125) / 1e9
        # predictor-drop decision clocks
        pd_dec = {}
        for th in (0.3, 0.5):
            dec = None
            for sec in CKS:
                pc = PC.get((i, sec))
                if pc is not None and pc < th: dec = ck + sec / SLOT_S; break
            pd_dec[th] = dec
        for xi, (n, st, to) in enumerate(EXITS):
            dec = ce + to / SLOT_S
            if isinstance(st, float) and len(val):
                hit = np.nonzero(val <= (1 - st) * spent)[0]
                if len(hit): dec = min(dec, clk[hit[0]])
            elif isinstance(st, str):
                pdd = pd_dec[float(st[2:])]
                if pdd is not None and pdd > ce: dec = min(dec, pdd)
            v = None
            if not we_complete and (c is None or dec < cclock): v = curve_exit(dec)
            if v is None:
                if c is None and not we_complete: v = val[-1] if len(val) else 0.0
                elif n in grad_val: v = grad_val[n]; gk[xi] += 1
                else: v = np.nan
            out[xi] += v - spent - RT_COST - cost
    res = dict(i=i, res=out / len(PAIR), fill=filled / len(PAIR), why=why, gradexit=gk / len(PAIR), pre_share=pre_hits / len(PAIR),
               fill_vs=float(np.mean(nfill_vs)) if nfill_vs else np.nan, tries=tries_tot / len(PAIR))
    if mg is not None and P is not None and len(P):
        kk = last_before(P, mg["slot"] + 2, 0); pb, pq = pool_state_after(P, kk, mg)
        res["sniped"] = (pq / pb) < (mg["pquote"] / mg["pbase"]) * 0.999
    return res

if __name__ == "__main__":
    out = []
    for n_, r in enumerate(meta):
        if not r["ent"] or r["edge"] or (r["grad"] and not r["has_mig"]): continue
        if MODE == "pre" and r["V"] not in (90, 95, 100, 105, 108): continue
        out.append(sim_row(n_))
        if n_ % 2000 == 0: print(n_, len(out), f"{time.time() - t0:.0f}s", flush=True)
    tag = f"{MODE}_{SIZE}" + ("" if MED_MS == 66.0 else f"_{int(MED_MS)}ms")
    pickle.dump(dict(R=out, EXITS=EXITS, params=dict(R=R, DELTA=DELTA, W=W, A=A, TRY_COST=TRY_COST, FAIL_COST=FAIL_COST, MED_MS=MED_MS)),
                open(D + f"/sim_{tag}.pkl", "wb"))
    print("saved", tag, len(out), f"{time.time() - t0:.0f}s")
