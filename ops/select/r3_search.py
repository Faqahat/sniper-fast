#!/usr/bin/env python3
# ROUND 3 (read-only, offline): an EXACT-CONDITIONS filter for genuinely strong launches (real early demand + follow-
# through), not a few-second pump. Labels from f_label.py (after the creator's bundle, P0 = post-bundle price):
#   STRONG = no dump in the first 5 s (min >= 0.85x) AND >= 20 distinct outside buyers AND >= 10 SOL outside buys in 60 s
#            AND >= 1.3x at 60 s AND (>= 1.3x at 5 min OR the curve filled = graduated)
#   DUMP   = <= 0.85x within 5 s             DEAD = < 5 outside buyers and < 1 SOL outside buys in 60 s
# Beam search over conjunctions of single-feature conditions (thresholds at TRAIN quantiles) on TRAIN (run 1, first 60%),
# rules chosen on VAL (run 1, 60-80%), reported ONCE on two unseen periods: TEST1 (run 1 last 20%) and TEST2 (forward run).
# Tier A = known before we buy (create tx, bundle, dev / creator / bundle-wallet history, launch tool, fees, own stream);
# Tier B = + the create slot's buyers (decide at the end of the create slot, buy after it).
# usage: python3 r3_search.py <table_dump.jsonl.gz> <demand.jsonl.gz> <run2 start bt> <out dir>
import sys, os, json, gzip, math, collections
import numpy as np
TAB, DEM, FWD0, OUT = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]; os.makedirs(OUT, exist_ok=True)
FIXR = 0.03
dm = {}
for l in gzip.open(DEM, "rt"): x = json.loads(l); dm[x["mint"]] = x
R = []
for l in gzip.open(TAB, "rt"):
    r = json.loads(l)
    if r.get("quote_sol") == 1 and (r.get("max_vsol") or 0) <= 200 and r.get("bt") and r["mint"] in dm and r.get("E_bundle_h5s") is not None:
        r.update(dm[r["mint"]]); R.append(r)
R.sort(key=lambda r: (r["bt"], r["S"])); N = len(R)
bt = np.array([r["bt"] for r in R], float)
run1 = bt < FWD0; n1 = run1.sum(); idx = np.arange(N)
SETS = {"TRAIN": run1 & (idx < int(n1 * .6)), "VAL": run1 & (idx >= int(n1 * .6)) & (idx < int(n1 * .8)), "TEST1": run1 & (idx >= int(n1 * .8)), "TEST2": ~run1}
hrs = {k: (bt[m].max() - bt[m].min()) / 3600 for k, m in SETS.items()}
a = lambda k, d=np.nan: np.array([(r.get(k) if isinstance(r.get(k), (int, float)) and not isinstance(r.get(k), bool) else d) for r in R], float)
grad = np.array([r.get("d_grad_s") is not None and r["d_grad_s"] <= 300 for r in R])
DUMP = a("d_min5s") <= 0.85
DEAD = (a("d_ub_60s") < 5) & (a("d_bsol_60s") < 1)
LABEL = os.environ.get("LABEL", "strict")
if LABEL == "strict": STRONG = ~DUMP & (a("d_ub_60s") >= 20) & (a("d_bsol_60s") >= 10) & (a("d_px60") >= 1.3) & ((a("d_px5m") >= 1.3) | grad)
elif LABEL == "trade":  # a real win for us first in line after the bundle: first-sell exit nets > +5% after all costs, and real demand
    STRONG = (a("E_bundle_fsell_30s_eos") - FIXR > 0.05) & ~DUMP & (a("d_ub_60s") >= 10)
else:                 # GOOD = real demand + it holds: >= 10 outside buyers and >= 5 SOL in 60 s, no dump in 5 s, >= 1.1x at 60 s and still >= 1.0x at 5 min
    STRONG = ~DUMP & (a("d_ub_60s") >= 10) & (a("d_bsol_60s") >= 5) & (a("d_px60") >= 1.1) & ((a("d_px5m") >= 1.0) | grad)
DEPTH = int(os.environ.get("DEPTH", "4")); MINSUP = int(os.environ.get("MINSUP", "60"))
for k, m in SETS.items():
    print(f"{k:6} {m.sum():6} launches {hrs[k]:5.1f} h | strong {STRONG[m].mean():5.1%}  dump-now {DUMP[m].mean():5.1%}  dead {DEAD[m].mean():5.1%}")
# ---- features (with the tier each needs)
TA = ["dev_buy", "glued_n", "glued_wallets", "glued_sol", "dev_share", "bundle_avg", "glued_same_payer", "glued_payer_is_creator", "payer_is_creator", "mayhem",
      "create_cup", "create_cul", "create_tips", "P0_mc_sol", "name_len", "sym_len", "name_upper", "name_digits", "sym_eq_name", "hour_utc",
      "heat_launches_10m", "heat_win_rate_60m", "wave_name_10m", "wave_name_60m", "wave_sym_60m", "cr_creates_window", "cr_min_since_prev_create",
      "h_cr_n", "h_cr_wins", "h_cr_last_win", "h_name_n", "h_name_wins", "h_bund_seen", "h_bund_launches", "h_bund_wins",
      "hd_cr_n", "hd_cr_fast", "hd_cr_first_s", "hd_cr_out_s", "hd_bw_seen", "hd_bw_fast", "hd_bw_first_s", "hd_bw_worst", "hd_dev_n", "hd_dev_fast"]
TB = ["fslot_nb", "fslot_ub", "fslot_bsol", "fslot_maxb", "fslot_ns", "fslot_ssol", "fslot_dev_sold", "fslot_bundle_sold", "fslot_cup_med", "fslot_tips", "fslot_px", "slot_buys", "slot_buy_sol", "slot_buyers", "slot_sells"]
CATS = {"uri_host": None, "create_variant": None}
TRN = SETS["TRAIN"]
atoms = []                                   # (label, mask)
def add_num(k):
    v = a(k); t = v[TRN & ~np.isnan(v)]
    if len(t) < 100: return
    qs = np.unique(np.round(np.quantile(t, [.1, .2, .3, .4, .5, .6, .7, .8, .9]), 3))
    for q in qs:
        atoms.append((f"{k} >= {q:.4g}", v >= q)); atoms.append((f"{k} <= {q:.4g}", v <= q))
    if np.isnan(v).any(): atoms.append((f"{k} known", ~np.isnan(v))); atoms.append((f"{k} unknown (no history)", np.isnan(v)))
for k in CATS:
    vals = collections.Counter(r.get(k) or "" for r, t in zip(R, TRN) if t).most_common(10)
    for v, c in vals:
        if c >= 100:
            mm = np.array([(r.get(k) or "") == v for r in R]); atoms.append((f"{k} == {v}", mm)); atoms.append((f"{k} != {v}", ~mm))
def wilson_lb(p, n, z=1.64): return 0 if n == 0 else (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n)
def score(m, s="TRAIN"):
    mm = m & SETS[s]; n = mm.sum()
    if n == 0: return -1, 0
    st, du, de = STRONG[mm].mean(), DUMP[mm].mean(), DEAD[mm].mean()
    return wilson_lb(st, n) - 0.5 * du - 0.25 * de, n
def search(feats, tag, minsup):
    global atoms
    atoms = []
    for k in feats: add_num(k)
    for k in CATS: pass
    if tag == "A":
        for k in CATS:
            vals = collections.Counter(r.get(k) or "" for r, t in zip(R, TRN) if t).most_common(10)
            for v, c in vals:
                if c >= 100:
                    mm = np.array([(r.get(k) or "") == v for r in R]); atoms.append((f"{k} == {v}", mm)); atoms.append((f"{k} != {v}", ~mm))
    beam = [((), np.ones(N, bool))]; pool = {}
    for depth in range(DEPTH):
        cand = []
        for conds, m in beam:
            used = {c.split(" ")[0] for c in conds}
            for lab, am in atoms:
                if lab.split(" ")[0] in used: continue
                nm = m & am; sc, n = score(nm)
                if n < minsup: continue
                cand.append((sc, conds + (lab,), nm))
        cand.sort(key=lambda x: -x[0]); seen = set(); beam = []
        for sc, conds, nm in cand:
            key = tuple(sorted(conds))
            if key in seen: continue
            seen.add(key); beam.append((conds, nm)); pool[key] = (conds, nm)
            if len(beam) >= 40: break
        print(f"  tier {tag} depth {depth + 1}: best train score {cand[0][0]:.3f} ({' AND '.join(cand[0][1])})", flush=True)
    return list(pool.values())
def report(conds, m, sets=("TRAIN", "VAL", "TEST1", "TEST2"), ent="E_bundle"):
    out = {}
    for s in sets:
        mm = m & SETS[s]; n = int(mm.sum())
        if n == 0: out[s] = dict(n=0); continue
        ret = {ex: float(np.nanmean(a(f"{ent}_{ex}")[mm] - FIXR)) for ex in ("fsell_30s_eos", "h30s", "h60s", "trail20_10_s15_2m", "trail30_20_s30_10m", "tp50_sl30_5m")}
        out[s] = dict(n=n, per_h=n / hrs[s], strong=float(STRONG[mm].mean()), dump=float(DUMP[mm].mean()), dead=float(DEAD[mm].mean()),
                      ub60_med=float(np.median(a("d_ub_60s")[mm])), bsol60_med=float(np.median(a("d_bsol_60s")[mm])), px5m_med=float(np.median(a("d_px5m")[mm])), ret=ret,
                      real=float(np.nanmean(a(f"E_k2_trail20_10_s15_2m")[mm] - FIXR)), slot=float(np.nanmean(a(f"E_slot_trail20_10_s15_2m")[mm] - FIXR)))
    return out
RES = {}
for tag, feats, ms in (("A", TA, MINSUP),) + ((("B", TA + TB, MINSUP),) if os.environ.get("TIERB") else ()):
    rules = search(feats, tag, ms)
    sc = []
    for conds, m in rules:
        v, n = score(m, "VAL")
        if n >= max(25, MINSUP // 3): sc.append((v, conds, m))
    sc.sort(key=lambda x: -x[0])
    RES[tag] = [dict(conds=list(c), val_score=v, **report(c, m, ent="E_bundle" if tag == "A" else "E_s1")) for v, c, m in sc[:8]]
json.dump(RES, open(os.path.join(OUT, f"r3_rules_{LABEL}.json"), "w"), indent=1)
base = {s: dict(strong=float(STRONG[m].mean()), dump=float(DUMP[m].mean()), dead=float(DEAD[m].mean())) for s, m in SETS.items()}
json.dump(base, open(os.path.join(OUT, "r3_base.json"), "w"))
for tag in RES:
    print(f"\n=== TIER {tag}: top rules chosen on VAL (then reported on unseen TEST1 = run 1 last 20%, TEST2 = forward run)")
    for k, x in enumerate(RES[tag][:5], 1):
        print(f" #{k} " + "  AND  ".join(x["conds"]))
        for s in ("TRAIN", "VAL", "TEST1", "TEST2"):
            y = x[s]
            if not y.get("n"): print(f"     {s:6} n=0"); continue
            print(f"     {s:6} n={y['n']:4} ({y['per_h']:4.1f}/h) strong {y['strong']:5.1%} (base {base[s]['strong']:.1%})  dump {y['dump']:5.1%} (base {base[s]['dump']:.1%})  dead {y['dead']:5.1%}"
                  f" | buyers/60s med {y['ub60_med']:.0f}, SOL/60s med {y['bsol60_med']:.1f}, price@5m med {y['px5m_med']:.2f}x"
                  f" | trade: first-sell {y['ret']['fsell_30s_eos']:+.1%} hold60s {y['ret']['h60s']:+.1%} trail {y['ret']['trail20_10_s15_2m']:+.1%} trail30/20 {y['ret']['trail30_20_s30_10m']:+.1%} tp50/sl30 {y['ret']['tp50_sl30_5m']:+.1%}"
                  f" | behind 2 buyers trail {y['real']:+.1%}, after slot trail {y['slot']:+.1%}")
