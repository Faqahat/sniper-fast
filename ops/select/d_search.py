#!/usr/bin/env python3
# PHASE D (read-only, offline): systematic token-selection rule search with strict time-ordered validation.
#   split by create time: TRAIN first 50% | VALIDATION next 25% | TEST last 25% (test is touched once, for the shortlist)
#   rules: single thresholds (train quantiles), categorical values, AND-pairs and AND-triples of the best singles
#   each rule is only allowed features a sniper could know at that entry (tiers); exit chosen on TRAIN only
#   net return per trade = simulated gross return (exact curve replay, pump fees) - FIX/size fixed cost
# usage: python3 d_search.py <table.jsonl.gz> <out dir> [FIX_SOL=0.015]
import sys, os, json, gzip, math, itertools, collections
import numpy as np
T, OUT = sys.argv[1], sys.argv[2]; FIX = float(sys.argv[3]) if len(sys.argv) > 3 else 0.015; SIZE = 0.5
os.makedirs(OUT, exist_ok=True)
R = [json.loads(l) for l in gzip.open(T, "rt")]
R = [r for r in R if r.get("quote_sol") == 1 and (r.get("max_vsol") or 0) <= 200 and r.get("bt")]
R.sort(key=lambda r: (r["bt"], r["S"]))
N = len(R); bt = np.array([r["bt"] for r in R], float)
tr = np.arange(N) < int(N * 0.5); va = (np.arange(N) >= int(N * 0.5)) & (np.arange(N) < int(N * 0.75)); te = np.arange(N) >= int(N * 0.75)
period = ((bt - bt.min()) // (3 * 3600)).astype(int)
# ---------------- targets ----------------
ENTRY_TIERS = {"E_bundle": {"T0", "T0b", "T1", "H"}, "E_k1": {"T0", "T0b", "T1", "H"}, "E_k2": {"T0", "T0b", "T1", "H"}, "E_k3": {"T0", "T0b", "T1", "H"}, "E_slot": {"T0", "T0b", "T1", "H", "Fslot"}, "E_s1": {"T0", "T0b", "T1", "H", "Fslot"},
               "E_1s": {"T0", "T0b", "T1", "H", "Fslot", "F1"},
               "E_5s": {"T0", "T0b", "T1", "H", "Fslot", "F1", "T2", "EB1"}, "E_15s": {"T0", "T0b", "T1", "H", "Fslot", "F1", "F5", "T2", "EB1", "EB5"}}
keys = sorted({k for r in R[:3000] for k in r if k.startswith("E_") and not k.endswith("entry_px")})
TGT = {}
for k in keys:
    en = "_".join(k.split("_")[:2])
    v = np.array([r.get(k) if r.get(k) is not None else np.nan for r in R], float)
    TGT[k] = (en, v - FIX / SIZE)
# ---------------- features + tiers ----------------
T0 = {"dev_buy", "create_cup", "create_cul", "create_tips", "create_cu", "create_idx", "create_fee", "mayhem", "name_len", "sym_len", "name_upper", "name_digits",
      "name_nonascii", "sym_eq_name", "payer_is_creator", "hour_utc", "heat_launches_10m", "wave_name_10m", "wave_name_60m", "wave_sym_60m", "cr_creates_window",
      "cr_min_since_prev_create"}
T1 = {"cr_prior_n", "cr_prior_fail", "cr_age_s", "cr_last_tx_s", "cr_recent_creates", "cr_same_name_before", "fund_amt", "fd_creators_so_far", "fd_is_creator"}
T2 = {"meta_ok", "desc_len", "has_tw", "has_tg", "has_web", "tw_status", "tw_community", "web_same_as_tw", "meta_keys"}
def tier(k):
    if k in T0: return "T0"
    if k in T1: return "T1"
    if k in T2: return "T2"
    if k.startswith("glued_") or k in ("P0_mc_sol", "dev_share", "bundle_avg"): return "T0b"
    if k.startswith("h_") or k == "heat_win_rate_60m": return "H"
    if k.startswith("slot_") or k.startswith("fslot_"): return "Fslot"
    if k.startswith("f1s_"): return "F1"
    if k.startswith("f5s_"): return "F5"
    if k.startswith("eb1s_"): return "EB1"
    if k.startswith("eb5s_"): return "EB5"
    return None
CAT = {"create_variant": "T0", "uri_host": "T0", "fp": "T0", "web_host": "T2", "img_host": "T2", "created_on": "T2"}
num_keys = sorted({k for r in R for k, v in r.items() if isinstance(v, (int, float)) and not isinstance(v, bool) and tier(k)})
F = {k: np.array([r.get(k) if isinstance(r.get(k), (int, float)) else np.nan for r in R], float) for k in num_keys}
rules = []                       # (name, tier set, mask)
for k in num_keys:
    x = F[k]; xt = x[tr & ~np.isnan(x)]
    if len(xt) < 200 or len(np.unique(xt)) < 2: continue
    qs = np.unique(np.quantile(xt, np.arange(0.05, 0.96, 0.05)))
    for q in qs:
        rules.append((f"{k} >= {q:.6g}", {tier(k)}, x >= q)); rules.append((f"{k} <= {q:.6g}", {tier(k)}, x <= q))
for k, tr_ in CAT.items():
    vals = collections.Counter(r.get(k) or "" for r, t_ in zip(R, tr) if t_)
    for v, c in vals.most_common(12):
        if c >= 150: rules.append((f"{k} == {v!r}", {tr_}, np.array([(r.get(k) or "") == v for r in R])))
print(f"launches {N} (SOL-quoted, sane reserves); train {tr.sum()} val {va.sum()} test {te.sum()}; single rules {len(rules)}; targets {len(TGT)}", flush=True)

def stats(ret, mask):
    v = ret[mask]; v = v[~np.isnan(v)]
    if len(v) == 0: return None
    pnl = v * SIZE; pos = pnl[pnl > 0].sum(); neg = -pnl[pnl < 0].sum()
    cum = np.cumsum(pnl); dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], cum])) - np.concatenate([[0], cum])))
    return dict(n=int(len(v)), win=float((v > 0).mean()), mean=float(v.mean()), median=float(np.median(v)), pf=float(pos / neg) if neg > 0 else float("inf"),
                exp_sol=float(pnl.mean()), total_sol=float(pnl.sum()), maxdd_sol=dd, winners=int((v > 0).sum()), losers=int((v <= 0).sum()),
                ci10=float(np.percentile([np.random.default_rng(i).choice(v, len(v)).mean() for i in range(200)], 10)) if len(v) >= 10 else None)

def best_target(mask, tiers):
    best = None
    for k, (en, ret) in TGT.items():
        if not tiers <= ENTRY_TIERS[en]: continue
        v = ret[mask & tr]; v = v[~np.isnan(v)]
        if len(v) < 150: continue
        m = v.mean()
        if best is None or m > best[1]: best = (k, m, len(v))
    return best

# baselines
base = []
for k, (en, ret) in TGT.items():
    s = {p: stats(ret, m) for p, m in (("train", tr), ("val", va), ("test", te))}
    base.append((k, s))
base.sort(key=lambda x: -(x[1]["train"] or {"mean": -9})["mean"])
# singles
scored = []
for nm, tiers, mask in rules:
    b = best_target(mask, tiers)
    if b and b[1] > 0: scored.append((b[1], nm, tiers, mask, b[0]))
scored.sort(key=lambda x: -x[0])
top = scored[:80]
print(f"singles with positive train mean: {len(scored)}", flush=True)
# pairs and triples among the top singles (different features)
feat = lambda nm: nm.split(" ")[0]
combos = []
for a, b in itertools.combinations(top, 2):
    if feat(a[1]) == feat(b[1]): continue
    m = a[3] & b[3]; t_ = a[2] | b[2]; bb = best_target(m, t_)
    if bb and bb[1] > 0: combos.append((bb[1], f"{a[1]} AND {b[1]}", t_, m, bb[0]))
combos.sort(key=lambda x: -x[0])
trip = []
for c in combos[:60]:
    for s_ in top[:40]:
        if feat(s_[1]) in c[1]: continue
        m = c[3] & s_[3]; t_ = c[2] | s_[2]; bb = best_target(m, t_)
        if bb and bb[1] > c[0]: trip.append((bb[1], f"{c[1]} AND {s_[1]}", t_, m, bb[0]))
trip.sort(key=lambda x: -x[0])
cands = scored[:300] + combos[:400] + trip[:300]
n_tested = len(rules) + len(combos) + len(trip)
print(f"pairs {len(combos)} triples {len(trip)}; candidates to validate {len(cands)}; rules evaluated {n_tested}", flush=True)
# validation gate (train-chosen exit), then the test set once
passed = []
for trm, nm, tiers, mask, tk in cands:
    ret = TGT[tk][1]; sv = stats(ret, mask & va)
    if not sv or sv["n"] < 40 or sv["mean"] <= 0 or sv["pf"] <= 1.05: continue
    passed.append((nm, tiers, mask, tk, stats(ret, mask & tr), sv))
# de-duplicate near-identical masks
final = []; seen = []
for p in sorted(passed, key=lambda p: -(p[5]["ci10"] or -9)):
    if any((p[2] & q).sum() / max(1, (p[2] | q).sum()) > 0.8 for q in seen): continue
    seen.append(p[2]); final.append(p)
res = []
for nm, tiers, mask, tk, st_, sv in final[:60]:
    ret = TGT[tk][1]; stt = stats(ret, mask & te)
    per = {int(p): stats(ret, mask & (period == p)) for p in np.unique(period)}
    res.append(dict(rule=nm, tiers=sorted(tiers), target=tk, train=st_, val=sv, test=stt, by_period=per))
res.sort(key=lambda r: -((r["test"] or {}).get("mean", -9) if (r["test"] or {}).get("n", 0) >= 20 else -9))
json.dump(dict(N=N, FIX=FIX, n_rules_tested=n_tested, baselines=[dict(target=k, **{p: s[p] for p in s}) for k, s in base], strategies=res),
          open(os.path.join(OUT, f"search_fix{FIX}.json"), "w"), indent=1, default=str)
print(f"validated (deduped): {len(final)}; reported {len(res)}", flush=True)
for r in res[:25]:
    t_ = r["test"] or {}
    print(f"TEST n={t_.get('n', 0):4} mean={t_.get('mean', 0):+.3f} med={t_.get('median', 0):+.3f} win={t_.get('win', 0):.0%} pf={t_.get('pf', 0):.2f} | VAL n={r['val']['n']} mean={r['val']['mean']:+.3f} | {r['target']} | {r['rule']}")
