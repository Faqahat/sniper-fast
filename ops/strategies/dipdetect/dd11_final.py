#!/usr/bin/env python3
# Final table: baseline vs the proposed detectors on every split (R2 = R2-val slice only for trained detectors' thresholds;
# R2 rows here are the WHOLE R2 window = in-sample for the models), 35 / 50 / 75 ms, FRA+AMS (and FRA only), engine limits.
# Sizes: 0.55 SOL; "+size" = 1.0 SOL when the predicted EV >= 0.010 (replayed at 1.0 SOL from dd1_<day>_s1.npz).
import sys, json
import numpy as np
import dd_lib as L
DAYS = ("R2", "R3", "R1", "R4")
def preds(name):
    P = np.load(f"{L.OUT}/pred_{name}.npy"); out = {}; o = 0
    for day in DAYS:
        n = len(L.load(day)["k"]); out[day] = P[o:o + n]; o += n
    return out
if __name__ == "__main__":
    D = {day: L.load(day) for day in DAYS}
    PA = preds("v3_reg4_nof1"); PB = preds("v3_reg13_nof1")
    big = {}
    for day in DAYS:
        try:
            z = np.load(f"{L.OUT}/dd1_{day}_s1.npz"); a, b = L.WIN[day]; t = D[day]["t"]
            zt = z["bt"].astype(np.int64)
            # same rows as the 0.55 file (window mask re-derived on k)
            kk = D[day]["k"]; pos = np.searchsorted(z["k"], kk); assert (z["k"][pos] == kk).all()
            big[day] = dict(pnl=z["pnl"][pos], off=z["off"][pos], st=z["st"][pos], sin=z["sin"][pos])
        except FileNotFoundError: big[day] = None
    f = lambda d, k: L.feat(d, k)
    DET = {
        "BASE  IMIT1 top4, 1.3s/SL10 (live)": (lambda day, d: np.isfinite(d["f1"]) & (d["f1"] >= L.THR["top4"]), "c6_tpnone_sl10", None),
        "BASE+ IMIT1 top4, 0.85s TP10 (exit chosen on R2)": (lambda day, d: np.isfinite(d["f1"]) & (d["f1"] >= L.THR["top4"]), "c4_tp10_sl30", None),
        "RULE  drop>=10% & coh_20>=6 (distilled, R2)": (lambda day, d: (f(d, "drop_pct") >= 9.93) & (f(d, "coh_20") > 5), "c4_tpnone_slnone", None),
        "NEW-A reg4_nof1 >= 0.0041, 0.85s": (lambda day, d: PA[day] >= 0.0041, "c4_tpnone_slnone", None),
        "NEW-A + 1.0 SOL if EV >= 0.010": (lambda day, d: PA[day] >= 0.0041, "c4_tpnone_slnone", lambda day: PA[day] >= 0.010),
        "NEW-A strict (EV >= 0.010), 0.85s": (lambda day, d: PA[day] >= 0.010, "c4_tpnone_slnone", None),
        "NEW-B reg13_nof1 >= -0.0002, 1.3s/SL10 (R2-val pick)": (lambda day, d: PB[day] >= -0.0002, "c6_tpnone_sl10", None),
    }
    out = {}
    for nm, (mk, exn, bigsel) in DET.items():
        e = L.EXI[exn]
        print(f"\n### {nm}")
        for day in DAYS:
            d = D[day]; sel = mk(day, d); h = L.hours(d)
            if bigsel is not None:
                if big[day] is None: print(f"  {day}: no 1.0 SOL replay"); continue
                m = bigsel(day)
                dd = dict(d); dd["pnl"] = np.where(m[:, None, None], big[day]["pnl"], d["pnl"]); dd["off"] = np.where(m[:, None, None], big[day]["off"], d["off"])
            else: dd = d
            cells = []
            for latx, lat in enumerate((35, 50, 75)):
                o = L.sim(dd, sel, latx, e); of = L.sim(dd, sel, latx, e, servers=("f",))
                cells.append(f"{lat}ms {o['pnl']:+6.2f} ({o['pnl'] / h * 24:+6.2f}/24h) {o['fill']:4d}/{o['att']:4d} fills {100 * o['fill_rate']:3.0f}% {o['per_fill']:+.4f}/fill win {100 * o['winr']:2.0f}% [FRA {of['pnl']:+6.2f}]")
                out[f"{nm}|{day}|{lat}"] = [o["pnl"], o["fill"], o["att"], o["per_fill"], o["fill_rate"], o["winr"], of["pnl"], h]
            print(f"  {day} ({h:4.1f} h): " + "\n                ".join(cells))
    json.dump(out, open(f"{L.OUT}/dd11_final.json", "w"))
