#!/usr/bin/env python3
# Contest check + a simple executable filter distilled from the E_bundle model's picks (read-only, offline)
import sys, os, json
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "e_model.py")).read()
exec(src[:src.index("REPORT = {}")])
en = "E_bundle"; fk = [k for k, (tt, _) in cols.items() if tt in ENT[en]]; Bm = binize(np.column_stack([cols[k][1] for k in fk]), TR)
net = g("E_bundle_h5s") - FIX / SIZE; ok = ~np.isnan(net); y = (net > 0).astype(float)
_, f = fit(Bm, y, TR & ok, VA & ok)
for q in (0.01, 0.02):
    thr = np.quantile(f[VA & ok], 1 - q); pk = TE & ok & (f >= thr)
    sb, sbs = g("slot_buys")[pk], g("slot_buy_sol")[pk]
    print(f"TOP {q:.0%} test picks n={pk.sum()}: create-slot outside buys median {np.median(sb):.0f} (0 in {np.mean(sb == 0):.0%}, >=3 in {np.mean(sb >= 3):.0%}), "
          f"create-slot outside SOL median {np.median(sbs):.2f}; all launches: 0 in {np.mean(g('slot_buys')[TE & ok] == 0):.0%}")
    for e2 in ("E_bundle", "E_k1", "E_k2", "E_slot"):
        v = g(f"{e2}_h5s")[pk] - FIX / SIZE; v = v[~np.isnan(v)]
        print(f"   same picks, entry {e2:8}: mean {v.mean():+.3f} median {np.median(v):+.3f} win {np.mean(v > 0):.0%}")
# distilled human-readable filters, thresholds from the picks' profile; evaluated on every split
D = lambda k: g(k)
filters = {
 "F1 dev>=2 & bundle>=3 SOL & creator idle>=300s": (D("dev_buy") >= 2) & (D("glued_sol") >= 3) & (D("cr_last_tx_s") >= 300),
 "F2 F1 & funded>=3 SOL": (D("dev_buy") >= 2) & (D("glued_sol") >= 3) & (D("cr_last_tx_s") >= 300) & (D("fund_amt") >= 3),
 "F3 F1 & no create by this dev in last 15 min": (D("dev_buy") >= 2) & (D("glued_sol") >= 3) & (D("cr_last_tx_s") >= 300) & ~(D("cr_min_since_prev_create") < 15),
 "F4 dev>=2 & bundle>=2 wallets & idle>=300s & not mayhem": (D("dev_buy") >= 2) & (D("glued_wallets") >= 2) & (D("cr_last_tx_s") >= 300) & (D("mayhem") == 0),
 "F5 dev>=1 & idle>=350s": (D("dev_buy") >= 1) & (D("cr_last_tx_s") >= 350),
}
for nm, m in filters.items():
    print(nm)
    for e2, ex in (("E_bundle", "h5s"), ("E_bundle", "trail20_10_s15_2m"), ("E_k1", "h5s"), ("E_slot", "h5s")):
        col = f"{e2}_{ex}" if not ex.startswith("h") else f"{e2}_h{ex[1:]}"
        r = g(col) - FIX / SIZE
        out = []
        for lab, sp in (("train", TR), ("val", VA), ("test", TE)):
            s = stats(r[m & sp]); out.append(f"{lab} n={s['n']} {s['mean']:+.3f}/{s['median']:+.3f} pf={s['pf'] or 0:.2f}" if s else f"{lab} -")
        per = [stats(r[m & (period == p)]) for p in np.unique(period)]
        print(f"   {e2:8} {ex:18} " + " | ".join(out) + " | by 3h period: " + " ".join(f"{(s or {}).get('mean', 0):+.2f}" for s in per))
