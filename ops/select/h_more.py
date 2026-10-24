#!/usr/bin/env python3
# MORE STRATEGIES (read-only, offline, run-1 data, same 50/25/25 time split; choices on train/val, test reported once)
import sys, os, json, gzip, glob, re, collections
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "e_model.py")).read()
exec(src[:src.index("REPORT = {}")])
SPL = (("train", TR), ("val", VA), ("test", TE))
def line(nm, ret, m):
    out = []
    for lab, sp in SPL:
        s = stats(ret[m & sp]); out.append(f"{lab} n={s['n']:4} {s['mean']:+.3f}/{s['median']:+.3f} w{s['win']:.0%} pf{(s['pf'] or 0):.2f}" if s else f"{lab} -")
    per = [stats(ret[m & (period == p)]) for p in np.unique(period)]
    return f"{nm:70} " + " | ".join(out) + " | P " + " ".join(f"{(s or {}).get('mean', 0):+.2f}" for s in per)
def ret(col): return g(col) - FIX / SIZE
print("=== (1) LAUNCH-TOOL COHORTS at E_bundle, sell at first sell (end of slot) — cohorts with >=150 train launches ===")
r1 = ret("E_bundle_fsell_30s_eos")
for k in ("uri_host", "create_variant", "fp", "created_on"):
    vals = collections.Counter(r.get(k) or "" for r, t in zip(R, TR) if t)
    for v, c in vals.most_common(10):
        if c < 150: continue
        m = np.array([(r.get(k) or "") == v for r in R])
        print(line(f"{k} == {v!r}"[:70], r1, m))
print("\n=== (2) FOLLOW KNOWN PRO SNIPERS (66 wallets from ops/snipers/CANDIDATES.md, found on 10-21 data = before this run) ===")
pros = set(re.findall(r"`([1-9A-HJ-NP-Za-km-z]{32,44})`", open("/home/moiz/sniper/ops/snipers/CANDIDATES.md").read()))
EB = {}
for f in glob.glob("/home/moiz/sniper-data/collect/phaseB/*.jsonl.gz"):
    for l in gzip.open(f, "rt"):
        x = json.loads(l); EB[x["mint"]] = x.get("early_buyers") or []
first_pro = np.array([bool(EB.get(r["mint"])) and EB[r["mint"]][0][0] in pros for r in R])
any_pro_slot = np.array([any(b[0] in pros and b[1] == 0 for b in EB.get(r["mint"], [])[:10]) for r in R])
n_pro_slot = np.array([sum(1 for b in EB.get(r["mint"], [])[:10] if b[0] in pros and b[1] == 0) for r in R])
print(f"pros in list: {len(pros)}; launches whose FIRST outside buyer is a pro: {first_pro.sum()}; with >=1 pro in create slot: {any_pro_slot.sum()}")
for nm, m in (("first outside buyer is a pro", first_pro), (">=1 pro buys in create slot", any_pro_slot), (">=2 pros buy in create slot", n_pro_slot >= 2)):
    for en, ex in (("E_k1", "fsell_30s_eos"), ("E_k1", "h5s"), ("E_slot", "fsell_30s_eos"), ("E_slot", "h5s"), ("E_s1", "h5s")):
        col = f"{en}_h{ex[1:]}" if ex.startswith("h") else f"{en}_{ex}"
        print(line(f"{nm} -> {en} {ex}", ret(col), m))
print("\n=== (3) LAUNCHES WITHOUT A GLUED BUNDLE (dev buys alone), E_bundle = first buyer after the create ===")
nob = g("glued_n") == 0
for cond_nm, cm in (("all no-bundle", nob), ("no-bundle & dev>=1", nob & (g("dev_buy") >= 1)), ("no-bundle & dev>=2", nob & (g("dev_buy") >= 2)),
                    ("no-bundle & dev>=1 & idle>=300s", nob & (g("dev_buy") >= 1) & (g("cr_last_tx_s") >= 300)),
                    ("no-bundle & dev>=2 & idle>=300s", nob & (g("dev_buy") >= 2) & (g("cr_last_tx_s") >= 300))):
    for ex in ("fsell_30s_eos", "h5s"):
        print(line(f"{cond_nm} {ex}", ret(f"E_bundle_{ex}" if ex.startswith("f") else "E_bundle_h5s"), cm))
print("\n=== (4) MORE MODEL TARGETS at E_bundle (label = this exit's net > 0), top-k chosen on validation ===")
fk = [k for k, (tt, _) in cols.items() if tt in ENT["E_bundle"]]; Bm = binize(np.column_stack([cols[k][1] for k in fk]), TR)
best_scores = {}
for ex in ("sk1_10s_eos", "sk2_10s_eos", "sk3_10s_eos", "sv1_10s_eos", "fsell_30s_eos", "h3s", "h10s"):
    col = f"E_bundle_h{ex[1:]}" if ex.startswith("h") else f"E_bundle_{ex}"
    net = ret(col); ok = ~np.isnan(net); y = (net > 0).astype(float); _, f = fit(Bm, y, TR & ok, VA & ok)
    best_scores[ex] = f
    for q in (0.005, 0.01, 0.02, 0.05):
        thr = np.quantile(f[VA & ok], 1 - q); print(line(f"model({ex}) top {q:.1%}", net, ok & (f >= thr)))
print("\n=== (5) SIZE BY SCORE (model fsell_30s_eos): 1.5 SOL on top 0.5%, 1.0 on next 0.5%, 0.5 on next 1% (sizes relative; returns per SOL) ===")
f = best_scores["fsell_30s_eos"]; net = ret("E_bundle_fsell_30s_eos"); ok = ~np.isnan(net)
t05, t1, t2 = (np.quantile(f[VA & ok], 1 - q) for q in (0.005, 0.01, 0.02))
size = np.where(f >= t05, 1.5, np.where(f >= t1, 1.0, np.where(f >= t2, 0.5, 0.0)))
for lab, sp in SPL:
    m = sp & ok & (size > 0); pnl = net[m] * size[m]   # NOTE fixed cost already per 0.5 SOL; bigger size dilutes it, so this is conservative
    print(f"   {lab}: trades {m.sum()}, SOL deployed {size[m].sum():.1f}, PnL {pnl.sum():+.2f} SOL, return on deployed {pnl.sum() / max(size[m].sum(), 1e-9):+.3f}; flat 0.5 SOL on the same trades {(net[m] * 0.5).sum():+.2f} SOL")
