#!/usr/bin/env python3
"""PAPER AUDIT step 5: the calibration tables from pa4_calib's output (shadow rows vs live on the live-armed T2 windows).
usage: pa5_calib_tables.py CALIB.pkl X.pkl OUT.json"""
import sys, json, pickle, collections, statistics
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/obs/paper_audit")

SIZE = 0.696
FR = 0.012500000186264515


def live_gross(li):
    """SOL back after pump's fee - spend (the shadow's pnl definition), from the live sell landing"""
    if li.get("sell_sol") is None: return None
    return li["sell_sol"] * (1 - FR) / 1e9 - SIZE


def main(cp, xp, outp):
    C = pickle.load(open(cp, "rb")); X = pickle.load(open(xp, "rb"))
    wins = C["wins"]
    out = {"H_ms": C["H"]}
    # 1. live fixed costs per trip and the port's consistency at the live position
    fx = [W["live"]["realized"] - live_gross(W["live"]) for W in wins if W["live"].get("filled") and live_gross(W["live"]) is not None]
    out["live_fixed_cost_mSOL"] = {"n": len(fx), "mean": 1e3 * statistics.mean(fx), "median": 1e3 * statistics.median(fx), "p10": 1e3 * float(np.percentile(fx, 10)), "p90": 1e3 * float(np.percentile(fx, 90))}
    cons = []
    for W in wins:
        lp = ((W.get("port") or {}).get("clean") or {}).get("live_pos")
        if lp and lp.get("el_naive") is not None and live_gross(W["live"]) is not None:
            cons.append((lp["el_naive"], live_gross(W["live"])))
    d = [a - b for a, b in cons]
    out["consistency_live_pos"] = {"n": len(cons), "sum_port": sum(a for a, _ in cons), "sum_live_gross": sum(b for _, b in cons),
                                   "mean_diff_mSOL": 1e3 * statistics.mean(d) if d else None, "abs_diff_lt_1mSOL": sum(1 for x in d if abs(x) < 1e-3),
                                   "abs_diff_lt_5mSOL": sum(1 for x in d if abs(x) < 5e-3)}
    # 2. per row / D: fill agreement and P&L
    FIX = -statistics.mean(fx) if fx else 3.524e-3   # the live fixed cost per round trip (positive), realized basis
    tab = {}
    for var in ("kept", "clean"):
        for D in (0.0, 2.0, 5.0, 10.0, 20.0, 40.0):
            cnt = collections.Counter(); agg = collections.defaultdict(float); nah = []; ours_m = 0
            for W in wins:
                rv = ((W.get("port") or {}).get(var) or {})
                o = rv.get(D)
                if o is None: cnt["no_tape"] += 1; continue
                lf = W["live"]["filled"]; pf = o["fill"]
                cnt[("both" if lf and pf else "live_only" if lf else "row_only" if pf else "neither")] += 1
                lg = live_gross(W["live"]) if lf else None
                if lf: agg["live_real_all"] += W["live"]["realized"]
                if pf:
                    nah.append(o["n_ahead"]); ours_m += 1 if o.get("ours_ahead") else 0
                    for e in ("e2_slip_0.696", "e2_naive_0.696", "ecc_slip", "ecc_naive"):
                        if o.get(e) is not None: agg[f"row_{e}"] += o[e]
                if lf and pf:
                    agg["both_live_real"] += W["live"]["realized"]
                    if lg is not None: agg["both_live_gross"] += lg
                    for e in ("e2_slip_0.696", "e2_naive_0.696", "el_slip", "el_naive", "ecc_slip", "ecc_naive"):
                        if o.get(e) is not None: agg[f"both_{e}"] += o[e]
                elif lf:
                    agg["live_only_real"] += W["live"]["realized"]
                    if lg is not None: agg["live_only_gross"] += lg
                elif pf:
                    for e in ("e2_slip_0.696", "e2_naive_0.696", "ecc_slip", "ecc_naive"):
                        if o.get(e) is not None: agg[f"row_only_{e}"] += o[e]
                    cnt[f"row_only_dis_{W['live']['dis_why']}"] += 1
            n_row = cnt["both"] + cnt["row_only"]
            tab[f"{var}_D{int(D)}"] = {"counts": dict(cnt), "row_fills": n_row, "agree_fill_pct": 100.0 * (cnt["both"] + cnt["neither"]) / max(1, sum(cnt[x] for x in ("both", "live_only", "row_only", "neither"))),
                                       "recall_of_live_fills": cnt["both"] / max(1, cnt["both"] + cnt["live_only"]), "precision": cnt["both"] / max(1, n_row),
                                       "agg": dict(agg), "n_ahead_median": statistics.median(nah) if nah else None, "fills_with_our_trade_ahead": ours_m,
                                       "model_realized_e2_slip": agg["row_e2_slip_0.696"] - n_row * FIX, "model_realized_e2_naive": agg["row_e2_naive_0.696"] - n_row * FIX,
                                       "model_realized_ecc_slip": agg["row_ecc_slip"] - n_row * FIX, "model_realized_ecc_naive": agg["row_ecc_naive"] - n_row * FIX}
    out["rows"] = tab
    out["live_total_realized"] = sum(W["live"].get("realized", 0.0) for W in wins if W["live"]["filled"])
    out["live_fills"] = sum(1 for W in wins if W["live"]["filled"])
    out["live_fail_fees"] = sum(W["live"]["fail_fees"] for W in wins)
    # 3. landing: live n_between and the clean-tape count of trades between row a's crossing and the live fill
    nb = [W["live"].get("n_between") for W in wins if W["live"].get("n_between") is not None]
    nbx = [((W.get("port") or {}).get("clean") or {}).get("live_pos", {}).get("n_between_x") for W in wins]
    nbx = [x for x in nbx if x is not None]
    msx = [W["live"].get("ms_after_x_a") for W in wins if W["live"].get("ms_after_x_a") is not None]
    msf = [W["live"].get("ms_after_x_first") for W in wins if W["live"].get("ms_after_x_first") is not None]
    out["landing"] = {"live_n_between": dict(collections.Counter(min(x, 5) for x in nb)), "live_n_between_x_clean": dict(collections.Counter(min(x, 5) for x in nbx)),
                      "live_ms_after_x_blockclock_median": statistics.median(msx) if msx else None, "live_ms_after_x_feed_median": statistics.median(msf) if msf else None,
                      "live_ms_after_x_blockclock_pct": [float(np.percentile(msx, p)) for p in (10, 25, 50, 75, 90)] if msx else None}
    for D in (0.0, 5.0, 10.0):
        na = [((W.get("port") or {}).get("clean") or {}).get(D, {}).get("n_ahead") for W in wins if W["live"]["filled"]]
        na = [x for x in na if x is not None]
        out["landing"][f"row_D{int(D)}_n_ahead_on_live_filled"] = dict(collections.Counter(min(x, 5) for x in na))
    json.dump(out, open(outp, "w"), indent=1, default=str)
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1, default=str))
    print(f"{'variant':12s} {'rowfills':>8s} {'both':>5s} {'liveonly':>8s} {'rowonly':>7s} {'agree%':>6s} {'recall':>6s} {'prec':>5s} | both: live_real live_gross e2slip e2naive el_slip el_naive ecc_slip ecc_naive | model realized e2slip e2naive eccslip eccnaive | rowonly e2slip ecc_slip | ours-ahead")
    for k, v in tab.items():
        c = v["counts"]; a = v["agg"]
        print(f"{k:12s} {v['row_fills']:8d} {c.get('both',0):5d} {c.get('live_only',0):8d} {c.get('row_only',0):7d} {v['agree_fill_pct']:6.1f} {v['recall_of_live_fills']:6.2f} {v['precision']:5.2f} | "
              f"{a.get('both_live_real',0):+.3f} {a.get('both_live_gross',0):+.3f} {a.get('both_e2_slip_0.696',0):+.3f} {a.get('both_e2_naive_0.696',0):+.3f} {a.get('both_el_slip',0):+.3f} {a.get('both_el_naive',0):+.3f} {a.get('both_ecc_slip',0):+.3f} {a.get('both_ecc_naive',0):+.3f} | "
              f"{v['model_realized_e2_slip']:+.3f} {v['model_realized_e2_naive']:+.3f} {v['model_realized_ecc_slip']:+.3f} {v['model_realized_ecc_naive']:+.3f} | {a.get('row_only_e2_slip_0.696',0):+.3f} {a.get('row_only_ecc_slip',0):+.3f} | {v['fills_with_our_trade_ahead']}")
    print("live total realized", out["live_total_realized"], "fills", out["live_fills"], "fail fees", out["live_fail_fees"])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
