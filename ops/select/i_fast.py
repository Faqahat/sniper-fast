#!/usr/bin/env python3
# FAST model check (read-only, offline): same GBDT, but only features available with NO RPC at the moment the dev's
# bundle lands: create tx + bundle (T0/T0b), our own create stream (dev launch rate, name waves, heat) and local
# outcome history WITHOUT the funder (which needs an RPC lookup). Compared with the full model on the same split.
import sys, os, json
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "e_model.py")).read()
exec(src[:src.index("REPORT = {}")])
full = [k for k, (tt, _) in cols.items() if tt in ENT["E_bundle"]]
fast = [k for k in full if cols[k][0] in ("T0", "T0b", "H") and not k.startswith("h_fd")]
# LIVE: only what the engine can read from raw transactions in the feed + its own create stream (no tx meta like CU used,
# no outcome history that needs price tracking, no block index)
live = [k for k in fast if not k.startswith("h_") and k not in ("create_cu", "heat_win_rate_60m", "create_idx")]
print(f"features: full {len(full)}, fast {len(fast)}; removed: {sorted(set(full) - set(fast))}")
out = {}
live_h = [k for k in fast if k not in ("create_cu", "create_idx")]   # live + outcome history (history can lag minutes)
print(f"live {len(live)}; live+history {len(live_h)}")
for nm, fk in ((("LIVE+HIST", live_h),) if os.environ.get("ONLY_LIVEH") else (("LIVE", live),) if os.environ.get("ONLY_LIVE") else (("FULL", full), ("FAST", fast), ("LIVE", live))):
    Bm = binize(np.column_stack([cols[k][1] for k in fk]), TR)
    for ex in ("fsell_30s_eos", "fsell_30s", "sk1_10s_eos", "sk2_10s_eos", "h3s", "h5s"):
        col = f"E_bundle_h{ex[1:]}" if ex.startswith("h") else f"E_bundle_{ex}"
        net = g(col) - FIX / SIZE; ok = ~np.isnan(net); y = (net > 0).astype(float)
        _, f = fit(Bm, y, TR & ok, VA & ok)
        row = []
        for q in (0.005, 0.01, 0.02, 0.05):
            thr = np.quantile(f[VA & ok], 1 - q); s = stats(net[TE & ok & (f >= thr)])
            row.append(f"top {q:.1%}: n={s['n']:3} {s['mean']:+.3f}/{s['median']:+.3f} w{s['win']:.0%}" if s else f"top {q:.1%}: -")
        wf = []
        for p in range(2, int(period.max()) + 1):
            past = (period < p) & ok; cut = np.quantile(idx[past], .8); trw = past & (idx < cut); vaw = past & (idx >= cut); tew = (period == p) & ok
            _, fw = fit(Bm, y, trw, vaw, seed=p); thr = np.quantile(fw[vaw], .98); s = stats(net[tew & (fw >= thr)]); wf.append(f"{(s or {}).get('mean', 0):+.3f}")
        print(f"{nm} {ex:14} AUC test {auc(y[TE & ok], f[TE & ok]):.3f} | " + " | ".join(row) + " | walk-forward top 2%: " + " ".join(wf), flush=True)
