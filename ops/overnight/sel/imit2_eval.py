#!/usr/bin/env python3
# IMIT2 retrain + out-of-sample comparison vs IMIT1 (local, offline, 10-24). Data: sel/imit2_rows_{r1,r2,r3,r7}.jsonl.gz from
# imit2_build.py (every dump inside the IMIT1 envelope; same 42 features; r1+r2 = the IMIT1 study data, checked identical).
# Recipe = sel_freeze.py: TRAIN split by time (fit first 80%, early stop on the last 20%), bin edges on the fit rows, GBDT
# 400 rounds lr 0.05 depth 3, thresholds top2 / top4 / top8 = quantiles of the score on the last 20% of TRAIN.
# Candidates: IMIT2a = same label (HkQ7hMjy / DYXDDrZC / haqqiUUX buy <= 1 s after the dump) with recent data added;
#             IMIT2b = broader label (any of the 10 top dip earners, topearners/work/top10.txt);
#             IMIT2c = OUR replay at 35 ms is a profitable fill (guard 1.05, tpnone_sl10_1.3s, after +0.0035 cost) - overfit-prone;
#             *_r = the same trained on R3 night data only (recent-only; extra, not a main candidate).
# Splits: A = TRAIN R1 + R2 + R3 night, TEST run-7 hours (10-24 08:04 -> 15:36 PKT);
#         B = TRAIN R1 + R2 + R3 night's first half, TEST R3 night's second half + run-7 hours;
#         C = TRAIN R1 + R2 (to 10-23 18:19), TEST the whole R3 night + run-7 hours.
# Decision metric = the bot's rule on TEST: near-leader dumps (Frankfurt list), score >= tier threshold, one position at a time
# (busy 1.6 s after a fill, 0.8 s after a blocked buy), 5 slots between picks on a token, 0.55 SOL, guard 1.05, exit no TP /
# SL -10% / 1.3 s, real costs (+0.0035 SOL per fill on top of the replay's tx costs, 0.0005 per blocked buy), at 35 / 50 ms.
# usage: python3 -I imit2_eval.py  [SEEDS=0,1,2] [EXT=1]  -> prints the tables, writes sel/imit2_eval[_ext].json (+ candidate models in MODELS_DIR)
#   EXT=1: TEST hours from the complete R3 extract (imit2_rows_g / r7f / t2 = 10-24 06:27 -> 16:27 PKT) instead of imit2_rows_r7; TRAIN unchanged
#   IMIT1rc = IMIT1's trees with top2 / top4 recomputed on the split's TRAIN tail (threshold-only control); 'IMIT1@n' = IMIT1 at the
#   candidate's TEST candidate count (threshold set on TEST: ranking diagnostic only)
import os, sys, json, gzip, time, collections
import numpy as np
D = "/home/moiz/sniper/ops/overnight/sel"; sys.path.insert(0, D)
import gbdt_np as G
from multiprocessing import Pool
MODELS_DIR = os.environ.get("MODELS_DIR", "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/imit2/models")
SEEDS = [int(s) for s in os.environ.get("SEEDS", "0,1,2").split(",")]
M1 = json.load(open(f"{D}/IMIT1.json")); FE = M1["features"]
EX = "tpnone_sl10_1.3s"; EXTRA, FAIL, GUARD, BUSY_F, BUSY_B, GAP = 0.0035, 0.0005, 1.05, 1600.0, 800.0, 5
LATS = (35, 50)
pkt = lambda t: time.strftime("%m-%d %H:%M", time.gmtime(t + 18000))

rows = []
EXT = os.environ.get("EXT") == "1"; TW = ("g", "r7f", "t2") if EXT else ("r7",); SUF = "_ext" if EXT else ""
for w in ("r1", "r2", "r3") + TW:
    for l in gzip.open(f"{D}/imit2_rows_{w}.jsonl.gz", "rt"):
        o = json.loads(l); o["win"] = w; rows.append(o)
N = len(rows)
X = np.array([[np.nan if v is None else v for v in o["x"]] for o in rows], float)
T = np.array([o["t"] for o in rows], float); MS = np.array([o["ms"] for o in rows]); SL = np.array([o["s"] for o in rows])
MINT = np.array([o["m"] for o in rows]); WIN = np.array([o["win"] for o in rows])
NEAR = np.array([bool(o["near"]) for o in rows]); F1 = np.array([o["f1"] for o in rows])
Y3 = np.array([bool(o["lab3"]) for o in rows]); YT = np.array([bool(o["labT"]) for o in rows])
def _our(o, L):
    v = o["ours"][str(L)]
    if not isinstance(v, dict): return 0, 0.0                 # no trade after our landing: nothing happens
    if v["ratio"] > GUARD: return 1, -FAIL                     # the guard blocks the buy
    return 2, v[EX] - EXTRA                                    # a fill
ST = {L: np.array([_our(o, L)[0] for o in rows]) for L in LATS}; PN = {L: np.array([_our(o, L)[1] for o in rows]) for L in LATS}
YP = (ST[35] == 2) & (PN[35] > 0)
R3 = WIN == "r3"; R7 = np.isin(WIN, TW); OLD = (WIN == "r1") | (WIN == "r2")
R3MID = float(np.median(T[R3]))                               # R3 night halves split at the median dump time
SPLITS = {"A": dict(train=OLD | R3, test=R7, recent=R3, halves=("run-7 1st half", "run-7 2nd half"), hsplit=float(np.median(T[R7]))),
          "B": dict(train=OLD | (R3 & (T < R3MID)), test=(R3 & (T >= R3MID)) | R7, recent=R3 & (T < R3MID), halves=("R3 night 2nd half", "run-7 hours"), hsplit=float(T[R7].min()) - 1),
          # C = models trained before the R3 night (R1 + R2 = IMIT1's study data incl. its own TEST hours), tested on the whole R3 night + day
          "C": dict(train=OLD, test=R3 | R7, recent=None, halves=("R3 night", "day hours"), hsplit=float(T[R3].max()))}
CANDS_OF = {"A": ("a", "b", "c", "a_r", "b_r"), "B": ("a", "b", "c", "a_r", "b_r"), "C": ("a", "b", "c")}

def score(model, Xm):
    Bm = np.zeros(Xm.shape, np.int16)
    for j, e in enumerate(model["edges"]):
        b = np.searchsorted(np.array(e), Xm[:, j], side="right") + 1; b[np.isnan(Xm[:, j])] = 0; Bm[:, j] = b
    f = np.full(len(Xm), model["F0"])
    for t in model["trees"]: f += model["lr"] * G.pred(t, Bm)
    return f

LABELS = {"a": (Y3, M1["label"]), "b": (YT, "any of the 10 top dip earners (haqqiUUX ssssswdk 9pQQc1xy sssssDdMN DYXDDrZC HkQ7hMjy E2x1ewwX BUkpShoE "
                                             "omegoMAe EMKY7r6U; full addresses in ops/agents/topearners/work/top10.txt) buys within 1000 ms after the dump (before the next big sell)"),
          "c": (YP, "OUR replay at 35 ms is a profitable fill: guard 1.05, 0.55 SOL, no TP / SL -10% / 1.3 s, P&L after +0.0035 SOL cost > 0")}
def train(job):
    split, cand, seed = job
    sp = SPLITS[split]; y, desc = LABELS[cand[0]]
    TRm = sp["recent"] if cand.endswith("_r") else sp["train"]
    cut = np.quantile(T[TRm], 0.8); FIT = TRm & (T < cut); VA = TRm & (T >= cut)
    edges = []
    for j in range(X.shape[1]):
        x = X[:, j]; xt = x[FIT & ~np.isnan(x)]
        edges.append(np.unique(np.quantile(xt, np.linspace(0, 1, 33)[1:-1])).tolist() if len(xt) else [])
    Bm = G.binize(X, FIT)
    trees, f = G.fit(Bm, y.astype(float), FIT, VA, rounds=400, lr=0.05, depth=3, seed=seed)
    p0 = y[FIT].mean(); F0 = float(np.log(p0 / (1 - p0)))
    thr = {f"top{int(q * 100)}": float(np.quantile(f[VA], 1 - q)) for q in (0.02, 0.04, 0.08)}
    name = f"IMIT2{cand}"
    tro = (f"split {split}: dumps {pkt(T[TRm].min())} -> {pkt(T[TRm].max())} PKT ({'R3 night only' if cand.endswith('_r') else 'R1 + R2 + R3 night' + (' 1st half' if split == 'B' else '')}; "
           f"fit first 80% to {pkt(cut)}, early stop + thresholds on the last 20%); seed {seed}")
    model = dict(name=name, trained_on=tro, label=desc, features=FE, cohort_file=M1["cohort_file"], envelope=M1["envelope"], edges=edges, F0=F0, lr=0.05,
                 trees=trees, thresholds=thr, exits=M1["exits"])
    assert np.allclose(score(json.loads(json.dumps(model)), X), f), "re-score from the JSON differs"
    return (split, cand, seed), model, f, int(FIT.sum()), int(VA.sum()), float(y[FIT].mean())

def sim(sc, thr, m, L, key="ms"):
    """the bot's rule over the rows in mask m (near leaders only), score >= thr; returns totals and per-row results"""
    if key == "ms": idx = np.where(m & NEAR & (sc >= thr))[0]; idx = idx[np.argsort(MS[idx], kind="stable")]
    else: idx = np.where(m & NEAR & (sc >= thr))[0]; idx = idx[np.lexsort((MS[idx], T[idx]))]
    busy = -1e30; last = {}; out = dict(sol=0.0, picks=0, fills=0, wins=0, blocked=0, cands=int(len(idx))); taken = []
    for i in idx:
        tt = MS[i] if key == "ms" else T[i]
        if tt < busy: continue
        if MINT[i] in last and SL[i] < last[MINT[i]] + GAP: continue
        last[MINT[i]] = SL[i]
        s = ST[L][i]
        if s == 0: continue
        out["picks"] += 1
        if s == 1: out["sol"] -= FAIL; out["blocked"] += 1; busy = tt + (BUSY_B if key == "ms" else BUSY_B / 1000); taken.append(i); continue
        p = PN[L][i]; out["sol"] += p; out["fills"] += 1; out["wins"] += int(p > 0); busy = tt + (BUSY_F if key == "ms" else BUSY_F / 1000); taken.append(i)
    out["taken"] = taken
    return out

def boot(sc_a, thr_a, sc_b, thr_b, m, L, t0, nb=20000, seed=7):
    """block bootstrap over clock hours of TEST: P(candidate - IMIT1 > 0) and the 5-95% range of the difference (SOL)"""
    ra, rb = sim(sc_a, thr_a, m, L), sim(sc_b, thr_b, m, L)
    hid = {h: j for j, h in enumerate(np.unique(np.floor((T[m] - t0) / 3600).astype(int)))}; H = len(hid)     # clock hours with TEST data
    def per_hour(r):
        v = np.zeros(H)
        for i in r["taken"]: v[hid[int((T[i] - t0) // 3600)]] += PN[L][i]
        return v
    d = per_hour(rb) - per_hour(ra); rng = np.random.default_rng(seed); bs = d[rng.integers(0, H, (nb, H))].sum(1)
    return float((bs > 0).mean()), float(np.quantile(bs, 0.05)), float(np.quantile(bs, 0.95)), H

if __name__ == "__main__":
    t_start = time.time()
    assert np.allclose(score(M1, X), F1, atol=1e-6), "IMIT1 score from the JSON != builder score"
    print(f"rows {N} (R1+R2 {int(OLD.sum())}, R3 night {int(R3.sum())}, run-7 {int(R7.sum())}); near {int(NEAR.sum())}; R3 night split at {pkt(R3MID)} PKT")
    # cross-check with dayguard_sum.py (IMIT1 wider tier, near = epoch-1066 schedule only, integer-second busy clock)
    near_cur = NEAR & (SL >= 460512000)
    for L in LATS:
        res = []
        for w in ("r3", "r7"):
            mm = (WIN == w) & near_cur; save = NEAR.copy(); NEAR[:] = near_cur
            r = sim(F1, M1["thresholds"]["top4"], WIN == w, L, key="t"); NEAR[:] = save; res.append(r)
        print(f"  dayguard cross-check {L} ms: night {res[0]['sol']:+.3f} ({res[0]['fills']} fills {res[0]['blocked']} blocked), "
              f"day {res[1]['sol']:+.3f} ({res[1]['fills']} fills {res[1]['blocked']} blocked)")
    os.makedirs(MODELS_DIR, exist_ok=True)
    jobs = [(sp, c, s) for sp in SPLITS for c in CANDS_OF[sp] for s in SEEDS]
    MOD = {}
    with Pool(int(os.environ.get("PROCS", "6"))) as p:
        for key, model, f, nfit, nva, pr in p.imap_unordered(train, jobs):
            MOD[key] = (model, f)
            json.dump(model, open(f"{MODELS_DIR}/IMIT2{key[1]}_split{key[0]}_seed{key[2]}.json", "w"))
            print(f"  trained {key}: {len(model['trees'])} trees, fit {nfit} rows (pos {pr:.3f}), va {nva}, thr top2 {model['thresholds']['top2']:+.3f} "
                  f"top4 {model['thresholds']['top4']:+.3f} ({time.time() - t_start:.0f} s)", flush=True)
    RES = {"meta": dict(rows=N, r3mid=pkt(R3MID), seeds=SEEDS), "splits": {}}
    for sp, S in SPLITS.items():
        m = S["test"]; t0 = float(T[m].min()); hrs = (T[m].max() - T[m].min()) / 3600
        print(f"\n===== split {sp}: TEST {pkt(T[m].min())} -> {pkt(T[m].max())} PKT ({hrs:.1f} h), {int(m.sum())} envelope dumps, {int((m & NEAR).sum())} near")
        out = {}
        TRm = S["train"]; VA1 = TRm & (T >= np.quantile(T[TRm], 0.8))
        M1rc = dict(M1, name="IMIT1rc", thresholds={f"top{int(q * 100)}": float(np.quantile(F1[VA1], 1 - q)) for q in (0.02, 0.04, 0.08)})
        models = [("IMIT1", 0, M1, F1), ("IMIT1rc", 0, M1rc, F1)] + [(f"IMIT2{c}", s, MOD[(sp, c, s)][0], MOD[(sp, c, s)][1]) for c in CANDS_OF[sp] for s in SEEDS]
        print("AUC on TEST (all envelope dumps / near only): label a (3 wallets) | label b (top 10) | label c (our profitable fill @35)")
        for name, seed, model, f in models:
            au = {lab: (G.auc(y[m].astype(int), f[m]), G.auc(y[m & NEAR].astype(int), f[m & NEAR])) for lab, y in (("a", Y3), ("b", YT), ("c", YP))}
            print(f"  {name:8s} s{seed}: " + " | ".join(f"{lab} {v[0]:.3f}/{v[1]:.3f}" for lab, v in au.items()))
            out.setdefault(name, {})[seed] = {"auc": au}
        print("P&L on TEST (bot rule; picks = attempted buys after busy/spacing; SOL after costs)")
        for tier in ("top4", "top2"):
            for L in LATS:
                print(f"  -- {tier} @ {L} ms")
                for name, seed, model, f in models:
                    thr = model["thresholds"][tier]; r = sim(f, thr, m, L)
                    h1 = sim(f, thr, m & (T <= S["hsplit"]), L); h2 = sim(f, thr, m & (T > S["hsplit"]), L)
                    line = (f"    {name:8s} s{seed}: thr {thr:+.3f} cands {r['cands']:4d} picks {r['picks']:3d} fills {r['fills']:3d} wins {r['wins']:3d} "
                            f"SOL {r['sol']:+7.3f} per fill {r['sol'] / max(1, r['fills']):+.4f} | {S['halves'][0]} {h1['sol']:+.3f} ({h1['fills']}) / {S['halves'][1]} {h2['sol']:+.3f} ({h2['fills']})")
                    if name != "IMIT1":
                        fv1 = np.sort(F1[m & NEAR])[::-1]; t1n = fv1[max(1, min(r["cands"], len(fv1))) - 1]; r1n = sim(F1, t1n, m, L)
                        line += f" | IMIT1@n {r1n['sol']:+.3f} ({r1n['fills']})"; out[name][seed][f"{tier}_{L}_imit1_at_n"] = r1n["sol"]
                        pb, lo, hi, H = boot(F1, M1["thresholds"][tier], f, thr, m, L, t0)
                        line += f" | vs IMIT1: P(better) {pb:.2f}, diff 5-95% [{lo:+.2f}, {hi:+.2f}] ({H} h)"
                        out[name][seed][f"{tier}_{L}_boot"] = (pb, lo, hi)
                    print(line)
                    out[name][seed][f"{tier}_{L}"] = {k: v for k, v in r.items() if k != "taken"} | {"h1": h1["sol"], "h2": h2["sol"], "h1_fills": h1["fills"], "h2_fills": h2["fills"]}
        # diagnostic (uses TEST to set thresholds -> INFERRED ranking quality only): same number of near candidates as IMIT1 top4
        print("diagnostic: each model at IMIT1-top4's candidate count on TEST (threshold set on TEST = ranking only)")
        k1 = int((m & NEAR & (F1 >= M1["thresholds"]["top4"])).sum())
        for name, seed, model, f in models:
            fv = np.sort(f[m & NEAR])[::-1]; thr = fv[min(k1, len(fv)) - 1]
            r35 = sim(f, thr, m, 35); r50 = sim(f, thr, m, 50)
            print(f"    {name:8s} s{seed}: {k1} cands | 35 ms {r35['sol']:+.3f} ({r35['fills']} fills) | 50 ms {r50['sol']:+.3f} ({r50['fills']} fills)")
            out[name][seed]["eqcount"] = (r35["sol"], r35["fills"], r50["sol"], r50["fills"])
        RES["splits"][sp] = out
    json.dump(RES, open(f"{D}/imit2_eval{SUF}.json", "w"))
    print(f"\ndone in {time.time() - t_start:.0f} s -> {D}/imit2_eval{SUF}.json; candidate models in {MODELS_DIR}")
