#!/usr/bin/env python3
"""PRESEND FILTER, analysis 1 (DEV ONLY: AMS r24 + r25): the base numbers and each ARM feature's separation of the filled windows.
Prints; touches no validation outcome."""
import json, sys, collections
import numpy as np
B = "/home/moiz/sniper-data/presend_filter"
W = [w for w in json.load(open(f"{B}/windows.json")) if w["run"] in ("ams:r24", "ams:r25")]


def base(ws, name):
    F = [w for w in ws if w["filled"]]
    net = sum(w["net"] for w in F) / 1e9; ff = sum(w["fail_fee"] for w in ws) / 1e9
    win = [w for w in F if w["net"] > 0]
    nt = [w for w in F if w.get("y_nb") == 0]
    flat = [w for w in F if w.get("y_nb", 0) > 0 and abs(w["net"]) < 4e6]
    print(f"{name}: windows {len(ws)} filled {len(F)} | fills net {net:+.4f} fail fees {ff:.4f} TOTAL {net - ff:+.4f} | winners {len(win)} {sum(w['net'] for w in win)/1e9:+.3f}"
          f" losers {len(F)-len(win)} {sum(w['net'] for w in F if w['net']<=0)/1e9:+.3f} | no-trade {len(nt)} {sum(w['net'] for w in nt)/1e9:+.3f} | flat(|net|<0.004, traded) {len(flat)} {sum(w['net'] for w in flat)/1e9:+.3f}")


for run in ("ams:r24", "ams:r25"): base([w for w in W if w["run"] == run], run)
base(W, "DEV")
F = [w for w in W if w["filled"] and w["chain_ok"]]
print("unfilled windows: n", sum(1 for w in W if not w["filled"]), "fail fees", round(sum(w["fail_fee"] for w in W if not w["filled"]) / 1e9, 4),
      "| filled windows' own fail fees", round(sum(w["fail_fee"] for w in W if w["filled"]) / 1e9, 4))
feats = [k for k in F[0] if isinstance(F[0][k], (int, float)) and not k.startswith("y_") and k not in
         ("seg", "w", "t", "trig_slot", "trig_idx", "en_slot", "n_att", "fail_fee", "n_fail", "filled", "spend", "net", "realized", "rent_back", "fill_slot", "fill_idx",
          "fill_t", "fill_send_t", "fill_send_slot", "chain_ok")]
y = np.array([w["net"] > 0 for w in F]); net = np.array([w["net"] for w in F]) / 1e9
print(f"\n{'feature':22s} {'win med':>9s} {'lose med':>9s} {'notrd med':>9s}  AUC(win)   best skip-low / skip-high with 0 winners removed")
for k in feats:
    x = np.array([float(w.get(k)) if w.get(k) is not None else np.nan for w in F])
    ok = ~np.isnan(x)
    if ok.sum() < 50: continue
    xw, xl = x[ok & y], x[ok & ~y]
    nt = np.array([w.get("y_nb") == 0 for w in F])
    # AUC
    from itertools import product
    r = np.argsort(np.argsort(np.r_[xw, xl], kind="stable"), kind="stable").astype(float)
    auc = (r[:len(xw)].sum() - len(xw) * (len(xw) - 1) / 2) / (len(xw) * len(xl)) if len(xw) and len(xl) else np.nan
    # zero-winner skip rules: skip x < t where t <= min over winners; skip x > t where t >= max over winners
    lo = xw.min(); hi = xw.max()
    sk_lo = ok & (x < lo); sk_hi = ok & (x > hi)
    print(f"{k:22s} {np.median(xw):9.3g} {np.median(xl):9.3g} {np.median(x[ok & nt]) if (ok & nt).any() else np.nan:9.3g}  {auc:5.2f}   "
          f"x<{lo:.3g}: {sk_lo.sum()} fills {net[sk_lo].sum():+.3f} | x>{hi:.3g}: {sk_hi.sum()} fills {net[sk_hi].sum():+.3f}")
