#!/usr/bin/env python3
"""PAPER AUDIT step 13: the per-row calibration table on the live-armed T2 windows (from pa4's port runs), restricted to the rows the
engine's shadow armed, step by step from the engine's own number to a live-comparable one:
  (1) engine records: tape WITH our live trades, 0.55 SOL, 2-slot exit, follower-drop model (= the dipmon paper line's ingredients)
  (2) the same at 0.696 SOL (curve math, not linear)          (3) tape WITHOUT our live trades (0.696, 2-slot exit, drop model)
  (4) + live-like exit (sell lands 296.5 ms after the fill on the real block clock = live median), drop model
  (5) (4) without the drop model (every follower kept)
Each as realized basis (gross - 3.524 mSOL per fill, MEASURED live fixed cost) and as cash (gross - 2.015 mSOL per fill). Live: the
same windows' realized / cash. Plus fill agreement and trades-ahead distributions.
usage: pa13_row_table.py CALIB.pkl X.pkl OUT.json"""
import sys, json, pickle, collections, statistics
import numpy as np

FIX_REAL = 3.523961e-3
FIX_CASH = (3523961 - 1508820) / 1e9
FR = 0.012500000186264515


def main(cp, xp, outp):
    C = pickle.load(open(cp, "rb")); X = pickle.load(open(xp, "rb"))
    wins = C["wins"]
    live_fills = sum(1 for W in wins if W["live"]["filled"])
    live_real = sum(W["live"].get("realized", 0.0) for W in wins if W["live"]["filled"])
    live_gross = sum(W["live"]["sell_sol"] * (1 - FR) / 1e9 - 0.696 for W in wins if W["live"].get("sell_sol") is not None)
    live_fail = sum(W["live"]["fail_fees"] for W in wins)
    live_cash = live_real + live_fills * 1508820 / 1e9 - live_fail
    out = {"live": {"windows": len(wins), "fills": live_fills, "gross": live_gross, "realized": live_real, "cash": live_cash, "fail_fees": live_fail}, "rows": {}}
    D = {"a": 0.0, "b": 5.0, "c": 10.0}
    for r, d in D.items():
        T = collections.defaultdict(float); n = collections.Counter(); ahead = collections.Counter()
        for W in wins:
            sh = (W.get("sh") or {}).get(r)
            if not sh or sh["armed"] is not True: continue
            n["armed"] += 1
            # (1) engine record
            if sh["fill"] and sh["pnl"] is not None: n["eng_fills"] += 1; T["eng_gross_055"] += sh["pnl"]
            k = ((W.get("port") or {}).get("kept") or {}).get(d)
            c = ((W.get("port") or {}).get("clean") or {}).get(d)
            lf = W["live"]["filled"]
            if k and k["fill"]:
                n["kept_fills"] += 1; T["kept_e2_slip_055"] += k.get("e2_slip_0.55", 0); T["kept_e2_slip_0696"] += k.get("e2_slip_0.696", 0)
                if k.get("ours_ahead"): n["kept_fills_our_trade_ahead"] += 1
            if c and c["fill"]:
                n["clean_fills"] += 1
                T["clean_e2_slip_0696"] += c.get("e2_slip_0.696", 0); T["clean_ecc_slip"] += c.get("ecc_slip", 0); T["clean_ecc_naive"] += c.get("ecc_naive", 0)
                n["both" if lf else "row_only"] += 1
                if lf: ahead[min(c["n_ahead"], 3)] += 1
                if not lf: T["row_only_ecc_slip"] += c.get("ecc_slip", 0)
            elif lf: n["live_only"] += 1
            else: n["neither"] += 1
            if lf: n["live_fills_in_armed"] += 1; T["live_real_in_armed"] += W["live"]["realized"]; T["live_cash_in_armed"] += W["live"]["realized"] + 1508820 / 1e9
            T["live_fail_in_armed"] += W["live"]["fail_fees"]
        R = {"counts": dict(n), "sums_gross": {k: round(v, 3) for k, v in T.items()}}
        R["realized_basis"] = {"1_engine_055": T["eng_gross_055"] - n["eng_fills"] * FIX_REAL,
                               "1b_engine_linear_to_0696": T["eng_gross_055"] * 0.696 / 0.55 - n["eng_fills"] * FIX_REAL,
                               "2_kept_0696_e2_slip": T["kept_e2_slip_0696"] - n["kept_fills"] * FIX_REAL,
                               "3_clean_0696_e2_slip": T["clean_e2_slip_0696"] - n["clean_fills"] * FIX_REAL,
                               "4_clean_0696_live_exit_slip": T["clean_ecc_slip"] - n["clean_fills"] * FIX_REAL,
                               "5_clean_0696_live_exit_naive": T["clean_ecc_naive"] - n["clean_fills"] * FIX_REAL,
                               "live": T["live_real_in_armed"]}
        R["agree_pct"] = 100 * (n["both"] + n["neither"]) / max(1, n["both"] + n["neither"] + n["row_only"] + n["live_only"])
        R["trades_ahead_on_both"] = dict(ahead)
        out["rows"][r] = R
    # live trades between the crossing and the fill (live record) and on the clean tape
    nb = collections.Counter(min(W["live"]["n_between"], 3) for W in wins if W["live"].get("n_between") is not None)
    out["live_trades_between_crossing_and_fill"] = dict(nb)
    ms = [W["live"]["ms_after_x_a"] for W in wins if W["live"].get("ms_after_x_a") is not None]
    out["live_ms_after_crossing_shadow_clock_pct"] = {p: round(float(np.percentile(ms, p)), 1) for p in (10, 25, 50, 75, 90)}
    for d in (20.0, 40.0):
        aa = collections.Counter(min(((W.get("port") or {}).get("clean") or {}).get(d, {}).get("n_ahead", 99), 3) for W in wins if W["live"]["filled"] and ((W.get("port") or {}).get("clean") or {}).get(d, {}).get("fill"))
        out[f"trades_ahead_D{int(d)}_on_live_filled"] = dict(aa)
    json.dump(out, open(outp, "w"), indent=1, default=str)
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
