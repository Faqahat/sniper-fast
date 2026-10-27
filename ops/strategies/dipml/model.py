#!/usr/bin/env python3
"""DIPML step 3: train (TRAIN), freeze threshold + size (VAL), score TEST once.
Per latency row L in 35/50/58/75 ms: target = replay value per attempt at 0.35 SOL
   y = ev - C * p_fill - R * (1 - p_fill)       C = 4.6 mSOL per filled round trip (live 4.3-4.9), R = 0.6 mSOL per revert
GBDT regression (squared loss, y clipped to +-50 mSOL), 400 rounds, depth 4, lr 0.05 - fixed in advance.
Calibration penalty (frozen from PRE-TEST live fires only, calib.json): mSOL per attempt, scaled by size / 0.35.
Selection on VAL: score cut (top q of VAL dumps, q grid) x size (0.35/0.5/0.75/1.0) maximising PENALISED VAL SOL/day
after position limits (2 wallets = 2 open positions, never the same token; a position is busy 8 slots).
Then TEST is scored ONCE with the frozen (model, cut, size) per row. Writes /home/moiz/sniper-data/dipml/frozen_L*.json,
results.json; prints the tables."""
import sys, json, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/dip")
import gbdt_np as gb
import core

DD = core.D
C, R = 0.0046, 0.0006
LATS = (35, 50, 58, 75); SIZES = (0.35, 0.5, 0.75, 1.0)
QS = (0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.12, 0.2, 0.3)

def fit_reg(B, y, tr, rounds=400, lr=0.05, depth=4, seed=0):
    rng = np.random.default_rng(seed); F = np.full(len(y), y[tr].mean()); trees = []
    rows_all = np.where(tr)[0]
    for it in range(rounds):
        gr = F - y; he = np.ones(len(y))
        rows = rng.choice(rows_all, size=len(rows_all) // 2, replace=False)
        fsub = np.sort(rng.choice(B.shape[1], size=max(4, int(B.shape[1] * 0.7)), replace=False))
        t = gb.build(B, gr, he, rows, depth, lam=1.0, min_n=200, fsub=fsub)
        F += lr * gb.pred(t, B); trees.append(t)
    return F, trees

def take(slots, mints, max_open=2, busy=8):
    o = np.argsort(slots, kind="stable"); took = np.zeros(len(slots), bool); open_ = []
    for q in o:
        s = slots[q]; open_ = [(e, mm) for e, mm in open_ if e >= s]
        if len(open_) >= max_open or any(mm == mints[q] for _, mm in open_): continue
        took[q] = True; open_.append((s + busy, mints[q]))
    return took

def days_of(slots_mask_sorted, D_slots):
    pass

def main():
    z = np.load(DD + "/dumps.npz"); e = np.load(DD + "/expect.npz")
    cal = json.load(open(DD + "/calib.json"))
    X = z["X"]; split = z["split"]; slot = z["slot"]; mint = z["mint"]; ok = e["ok"]
    hours = json.load(open(DD + "/hours.json"))
    B = gb.binize(X, (split == 0) & ok)
    res = {"hours": hours, "rows": {}}
    for L in LATS:
        pf = e[f"L{L}_S0.35_F0.0_pf"]; ev = e[f"L{L}_S0.35_F0.0_ev"]
        y = np.clip(ev - C * pf - R * (1 - pf), -0.05, 0.05)
        tr = (split == 0) & ok
        F, trees = fit_reg(B, y, tr)
        def val(sel, S, phi=0.0, pen=True, cost=C):
            pfS = e[f"L{L}_S{S}_F{phi}_pf"]; evS = e[f"L{L}_S{S}_F{phi}_ev"]
            v = evS - cost * pfS - R * (1 - pfS)
            if pen: v = v - cal["penalty_per_attempt"] * S / 0.35
            return v[sel], pfS[sel]
        best = None; grid = []
        for q in QS:
            vm = (split == 1) & ok
            cut = np.quantile(F[vm], 1 - q)
            cand = np.where(vm & (F >= cut))[0]
            tk = cand[take(slot[cand], mint[cand])]
            for S in SIZES:
                v, p = val(tk, S)
                day = v.sum() / hours["val"] * 24
                grid.append((q, S, round(day, 2), len(tk)))
                if best is None or day > best[2]: best = (q, S, day, float(cut))
        q, S, vday, cut = best
        out = {"q": q, "size": S, "cut": cut, "val_day_pen": vday, "val_grid": grid}
        json.dump({"L": L, "q": q, "size": S, "cut": cut, "trees": trees, "edges_from": "TRAIN binize", "feat": z["names"].tolist()},
                  open(DD + f"/frozen_L{L}.json", "w"), default=float)
        # ---- TEST, once ----
        tm = (split == 2) & ok
        cand = np.where(tm & (F >= cut))[0]; tk = cand[take(slot[cand], mint[cand])]
        T = {}
        for SS in SIZES:
            for phi in (0.0, 0.2):
                for pen in (False, True):
                    v, p = val(tk, SS, phi, pen)
                    T[f"S{SS}_F{phi}_{'pen' if pen else 'raw'}"] = {"day": v.sum() / hours["test"] * 24, "trades_day": len(tk) / hours["test"] * 24,
                                                                    "fills_day": p.sum() / hours["test"] * 24, "per_attempt_mSOL": v.mean() * 1e3,
                                                                    "win": float((e[f"L{L}_S{SS}_F{phi}_ev"][tk] - C > 0).mean())}
        # all-dumps and random baselines on TEST (same count), frozen size, penalised
        rng = np.random.default_rng(1); allc = np.where(tm)[0]
        rnd = []
        for _ in range(50):
            c2 = np.sort(rng.choice(allc, size=len(cand), replace=False)); t2 = c2[take(slot[c2], mint[c2])]
            rnd.append(val(t2, S)[0].sum() / hours["test"] * 24)
        out["test"] = T; out["test_random_median_day"] = float(np.median(rnd)); out["test_attempts"] = int(len(tk))
        # per-day split of TEST (10-26 vs 10-27) at frozen size, penalised
        v, _ = val(tk, S); out["test_halves"] = [float(v[slot[tk] < 462_099_218].sum()), float(v[slot[tk] >= 462_099_218].sum())]
        res["rows"][L] = out
        t = T[f"S{S}_F0.0_pen"]
        print(f"L{L}: frozen q={q} size={S} | VAL pen {vday:+.2f}/day | TEST raw {T[f'S{S}_F0.0_raw']['day']:+.2f} pen {t['day']:+.2f} "
              f"phi20 {T[f'S{S}_F0.2_raw']['day']:+.2f} pen+phi20 {T[f'S{S}_F0.2_pen']['day']:+.2f} /day | attempts {t['trades_day']:.0f}/day fills {t['fills_day']:.0f}/day "
              f"win {t['win']:.2f} | random {out['test_random_median_day']:+.2f} | halves {out['test_halves']}", flush=True)
    json.dump(res, open(DD + "/results.json", "w"), default=float, indent=1)

if __name__ == "__main__":
    main()
