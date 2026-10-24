#!/usr/bin/env python3
# ROUND 2b (read-only, offline): train the GBDT on the TRADE outcome itself (net return of a given entry+exit > 0),
# pick exit + score threshold on VALIDATION, report the untouched TEST and a walk-forward. Reuses e_model.py's code.
import sys, os, json
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "e_model.py")).read()
exec(src[:src.index("REPORT = {}")])
EXITS = ["fsell_30s_eos", "sk1_10s_eos", "sk2_10s_eos", "sk3_10s_eos", "sv1_10s_eos", "sk1_10s", "sk2_10s", "sk3_10s", "sk5_30s", "sv1_10s", "sv2_10s", "sv5_30s", "fsell_30s", "h3s", "h10s", "tp20_sl10_30s", "tp25_sl25_60s", "tp50_sl30_5m", "tp100_sl40_10m", "trail20_10_s15_2m", "trail30_20_s30_10m", "trail50_25_s30_10m", "h5s", "h60s"]
OUTR = {}
for en in [x for x in sys.argv[4].split(",")] if len(sys.argv) > 4 else ["E_bundle", "E_k1", "E_k2", "E_k3", "E_slot"]:
    tiers = ENT[en]; fk = [k for k, (tt, _) in cols.items() if tt in tiers]; X = np.column_stack([cols[k][1] for k in fk]); Bm = binize(X, TR)
    cand = []
    for ex in EXITS:
        col = f"{en}_{ex}" if not ex.startswith("h") else f"{en}_h{ex[1:]}"
        r = g(col)
        if np.isnan(r).all(): continue
        net = r - FIX / SIZE; ok = ~np.isnan(net); y = (net > 0).astype(float)
        trees, f = fit(Bm, y, TR & ok, VA & ok)
        for q in (0.01, 0.02, 0.05, 0.10):
            thr = np.quantile(f[VA & ok], 1 - q); sv = VA & ok & (f >= thr); st = TE & ok & (f >= thr)
            cand.append(dict(exit=ex, q=q, thr=float(thr), auc_val=auc(y[VA & ok], f[VA & ok]), val=stats(net[sv]), test=stats(net[st]),
                             by_period={int(p): stats(net[st & (period == p)]) for p in np.unique(period[TE])}, col=col, f=f, ok=ok))
    # choose on validation: best validation mean with >= 40 validation trades
    good = [c for c in cand if c["val"] and c["val"]["n"] >= 40]
    good.sort(key=lambda c: -c["val"]["mean"])
    print(f"== {en}: best 5 (exit, top-k) chosen on VALIDATION, then TEST", flush=True)
    for c in good[:5]:
        v, t = c["val"], c["test"] or {}
        print(f"   {c['exit']:20} top {c['q']:.0%} | AUC {c['auc_val']:.3f} | VAL n={v['n']} mean={v['mean']:+.3f} pf={v['pf'] or 0:.2f} | TEST n={t.get('n')} mean={t.get('mean', 0):+.3f} "
              f"med={t.get('median', 0):+.3f} win={t.get('win', 0):.0%} pf={t.get('pf') or 0:.2f} dd={t.get('maxdd_sol', 0):.2f} SOL", flush=True)
    if good:
        b = good[0]
        # walk-forward for the chosen exit/q
        net = g(b["col"]) - FIX / SIZE; ok = ~np.isnan(net); y = (net > 0).astype(float); wf = {}
        for p in range(2, int(period.max()) + 1):
            past = (period < p) & ok; cut = np.quantile(idx[past], .8); trw = past & (idx < cut); vaw = past & (idx >= cut); tew = (period == p) & ok
            _, fw = fit(Bm, y, trw, vaw, seed=p); thr = np.quantile(fw[vaw], 1 - b["q"]); wf[int(p)] = stats(net[tew & (fw >= thr)])
        print("   walk-forward of the chosen one: " + " | ".join(f"P{p}: n={(s or {}).get('n')} mean={(s or {}).get('mean', 0):+.3f}" for p, s in wf.items()), flush=True)
        acc = np.zeros(len(fk)); trees_b, fb = fit(Bm, y, TR & ok, VA & ok)
        for t in trees_b: imp(t, acc)
        print("   top features: " + ", ".join(f"{fk[j]} {acc[j] / acc.sum():.0%}" for j in np.argsort(-acc)[:10] if acc[j] > 0), flush=True)
        thr = np.quantile(fb[VA & ok], 1 - b["q"]); pick = ok & (fb >= thr)
        prof = {}
        for k in ("dev_buy", "glued_sol", "glued_wallets", "P0_mc_sol", "cr_last_tx_s", "cr_min_since_prev_create", "fund_amt", "create_cup", "create_cul", "heat_win_rate_60m", "dev_share"):
            if k in cols: x = cols[k][1]; prof[k] = (float(np.nanmedian(x[pick])), float(np.nanmedian(x[ok])))
        print("   picks vs all (median): " + ", ".join(f"{k} {a:.3g} vs {b_:.3g}" for k, (a, b_) in prof.items()), flush=True)
        OUTR[en] = dict(chosen={k: v for k, v in b.items() if k not in ("f", "ok")}, walk_forward=wf,
                        others=[{k: v for k, v in c.items() if k not in ("f", "ok")} for c in good[:10]])
json.dump(OUTR, open(os.path.join(OUT, f"trade_model_fix{FIX}.json"), "w"), indent=1, default=str)
