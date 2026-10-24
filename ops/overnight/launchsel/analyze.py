#!/usr/bin/env python3
# Launch-selection strategy search (local only). TRAIN = launches before 10-23 06:00 PKT, TEST = after (incl. the new live run R3).
# For each decision point and signal family: beam search of AND-rules (thresholds = TRAIN quantiles) maximizing TRAIN total P&L with
# >= MINPH picks/h; exit chosen on TRAIN among 8 exits; everything then measured on TEST. Also REJECT rules (dump / dead / no demand).
import sys, json, gzip, time, calendar, collections, statistics
import numpy as np
R = [json.loads(l) for l in gzip.open("/home/moiz/sniper/ops/overnight/launchsel/launches.jsonl.gz", "rt")]
SPLIT = calendar.timegm(time.strptime("2026-10-23 06:00", "%Y-%m-%d %H:%M")) - 18000
EXITS = ["h5s", "h30s", "h2m", "h10m", "tp30_sl20_2m", "tp50_sl25_5m", "tp100_sl30_10m", "tp200_sl40_10m"]
for r in R:
    h = r.get("img_host") or ""; r["img_axiom"] = int("axiom" in h); r["img_ipfs"] = int("ipfs" in h); r["img_other"] = int(bool(h) and not r["img_axiom"] and not r["img_ipfs"])
FAM = {"dev_creator": ["dev_buy", "create_fee", "prior_creates", "prior_n", "cr_prev", "cr_grad", "cr_best", "has_funder", "fu_prev", "fu_grad", "fu_best"],
       "metadata": ["tw", "tg", "web", "desc_len", "name_len", "sym_len", "meta_ok", "img_axiom", "img_ipfs", "img_other"],
       "bundle": ["bundle_n", "ins_n", "jito", "ins_sold", "dev_sold", "dev_buy"],
       "flow": ["n_buys", "n_sells", "uniq_out", "out_sol", "buy_sol", "sell_sol", "net", "bs_ratio", "top_share", "max_buy", "buys_1s", "sells_1s", "vsol", "chg", "dd",
                "since_last", "sold_absorbed", "slot01_out"],
       "smart": ["coh_n", "coh_sol", "tgt_n", "slot01_out", "uniq_out"]}
FAM["ALL"] = sorted(set(sum(FAM.values(), [])))
D0_OK = set(FAM["dev_creator"] + FAM["metadata"])
MINPH = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
def metrics(P, T):
    if not len(P): return None
    o = np.argsort(T); cum = np.cumsum(P[o]); dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], cum]))[1:] - cum)) if len(cum) else 0
    w = P[P > 0]; l = P[P <= 0]
    return dict(n=len(P), win=len(w) / len(P), avg=P.mean() / 0.5, med=float(np.median(P)) / 0.5, pf=(w.sum() / -l.sum()) if l.sum() < 0 else 99, exp=P.mean(), tot=P.sum(), dd=dd, W=len(w), L=len(l))
def fmt(m, hrs):
    if not m: return "no picks"
    return (f"n {m['n']:5d} ({m['n'] / hrs:5.1f}/h) win {m['win']:4.0%} avg {m['avg']:+6.1%} med {m['med']:+6.1%} PF {m['pf']:4.2f} exp {m['exp']:+.4f} SOL "
            f"tot {m['tot']:+7.2f} DD {m['dd']:5.2f} W/L {m['W']}/{m['L']}")
OUT = []
for d in (0, 1, 3, 10, 30):
    V = [r for r in R if r["d"] == d]; Tm = np.array([r["bt"] + d for r in V]); tr = Tm < SPLIT; te = ~tr
    HTR = (Tm[tr].max() - Tm[tr].min()) / 3600; HTE = (Tm[te].max() - Tm[te].min()) / 3600
    PX = {e: np.array([r["res"][e] for r in V]) for e in EXITS}
    RUN = np.array([r["runner"] for r in V]); DMP = np.array([r["dump"] for r in V]); DEAD = np.array([r["dead"] for r in V])
    print(f"\n================ DECISION {d} s after the create: TRAIN {tr.sum()} launches / {HTR:.1f} h, TEST {te.sum()} / {HTE:.1f} h")
    print(f"  base rates TEST: runner {RUN[te].mean():.1%} dump {DMP[te].mean():.1%} dead {DEAD[te].mean():.1%} | buy ALL, best exit: " +
          ", ".join(f"{e} {PX[e][te].sum():+.0f}" for e in ("h5s", "h30s", "tp30_sl20_2m", "tp100_sl30_10m")))
    for fam, feats in FAM.items():
        feats = [k for k in feats if d > 0 or k in D0_OK]
        if not feats: continue
        X = np.array([[float(r.get(k) or 0) for k in feats] for r in V])
        GR = {k: sorted(set(float(np.quantile(X[tr, j], q)) for q in np.linspace(0.05, 0.95, 19))) for j, k in enumerate(feats)}
        def mask(c):
            m = np.ones(len(V), bool)
            for k, op, v in c: j = feats.index(k); m &= (X[:, j] >= v) if op == ">=" else (X[:, j] <= v)
            return m
        def obj(c):
            m = mask(c) & tr
            if m.sum() / HTR < MINPH: return -1e9, None
            best = max(EXITS, key=lambda e: PX[e][m].sum()); return PX[best][m].sum(), best
        beam = [(obj([])[0], [])]; best = beam[0]
        for depth in range(4):
            cand = []
            for sc, c in beam:
                used = {(k, op) for k, op, _ in c}
                for k in feats:
                    for op in (">=", "<="):
                        if (k, op) in used: continue
                        for v in GR[k]: cc = c + [(k, op, v)]; cand.append((obj(cc)[0], cc))
            cand.sort(key=lambda x: -x[0]); beam = []; seen = set()
            for sc, c in cand:
                kk = tuple(sorted((k, op, round(v, 6)) for k, op, v in c))
                if kk in seen: continue
                seen.add(kk); beam.append((sc, c))
                if len(beam) >= 5: break
            if not beam or beam[0][0] <= best[0] + 1e-9: break
            best = beam[0]
        c = best[1]; ex = obj(c)[1]
        if ex is None: continue
        m = mask(c); mtr, mte = metrics(PX[ex][m & tr], Tm[m & tr]), metrics(PX[ex][m & te], Tm[m & te])
        rule = " AND ".join(f"{k} {op} {v:.4g}" for k, op, v in c) or "(everything)"
        print(f"\n  [{fam}] d={d}s  RULE: {rule}  | exit {ex}")
        print(f"     TRAIN {fmt(mtr, HTR)}\n     TEST  {fmt(mte, HTE)}")
        if m[te].any(): print(f"     TEST picks: runner {RUN[m & te].mean():.1%} (base {RUN[te].mean():.1%}) dump {DMP[m & te].mean():.1%} (base {DMP[te].mean():.1%}) dead {DEAD[m & te].mean():.1%} (base {DEAD[te].mean():.1%})")
        OUT.append(dict(d=d, fam=fam, rule=rule, exit=ex, train=mtr, test=mte))
json.dump(OUT, open("/home/moiz/sniper/ops/overnight/launchsel/strategies.json", "w"), default=float)
