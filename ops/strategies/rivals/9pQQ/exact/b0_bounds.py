#!/usr/bin/env python3
"""Necessary-condition scan: per feature, 0.5/1/5/50/95/99/99.5 pct among its buy triggers vs all flat rows (10-28+10-30)."""
import numpy as np, xlib as X
FE = ["side","size","vsol","vpre","impact","trader_cnt","age","age_bt","may","is_creator","dev_buy","ntr_sofar","ath","dd_ath","sg0","sg1","sg3","sg10","sg30","sg100",
      "nb0","nb1","ns1","dv1","dv3","dv10","dv30","dv100","slot_pos","since_obuy","since_osell","since_prev","k_done","since_own_sell","v_vs_ownsell","last_trip_ret","open_pos","own_buys25","bsol0","ssol0"]
for r in X.RUNS[:2] + X.RUNS[2:3]:
    z = np.load(f"{X.XOUT}/dm_{r}.npz"); flat = ~z["hold"]; y = z["yb_imm"] & flat
    print("==", r, "pos", y.sum(), "flat", flat.sum())
    for f in FE:
        a = z[f]; p = a[y]; q = a[flat]
        pp = np.nanpercentile(p, [0, 0.5, 1, 5, 50, 95, 99, 99.5, 100]); qq = np.nanpercentile(q, [1, 50, 99])
        print(f"{f:15s} his {np.round(pp,3)}  all {np.round(qq,3)}")
