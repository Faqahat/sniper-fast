#!/usr/bin/env python3
# GUARD SWEEP (owner 10-25 ~07:50 PKT: haqqiUUX fills 85% even when the price is already 5-10% above the post-dump price; is our
# +5% buy guard too tight?). Read-only replay on the study data: dd24_guard_build.py rebuilt every dump with NO guard at 0.35 SOL
# (dd1_<day>_s0.35_g1000.npz: same rows as dd1_<day>.npz, plus P&L for the rows the +5% guard used to block). Here the guard
# is re-applied as a threshold on `ratio` (price where our buy lands / price right after the dump):
#   fill if ratio <= g, else a failed buy (FAIL cost, 0.8 s busy) -- exactly what dd_lib.sim does with the stored status.
# Picks: IMIT1 top4 inside the study envelope (what Amsterdam trades) and M2 >= its live threshold inside the envelope
# (Frankfurt's gate). Exits: c4_tpnone_slnone (today's A/B runs: 5-slot hold, no stop) and c6_tpnone_sl10 (runs 10-14).
# dd_lib.sim engine limits (one position per server, near-leader slots, FIX per fill), landing 35 / 50 / 75 ms.
# usage: python3 dd24_guard_eval.py [days...]   (default R1 R2 R3 R4)
import sys, json
import numpy as np
import dd_lib as L
import dd20_shadow_eval as D20

GUARDS = (1.05, 1.10, 1.15, 1.20, 1.30, 1e9)
DAYS = sys.argv[1:] or ["R1", "R2", "R3", "R4"]
EXITS = (("c4 (A/B runs, ~5 slots)", L.EXI["c4_tpnone_slnone"]), ("c6 SL10 (runs 10-14, 1.3 s)", L.EXI["c6_tpnone_sl10"]))
BUNDLE = f"{L.OUT}/m2_v3_reg4_top25.json"

def load_ng(day):
    """L.load, but from the no-guard rebuild (same rows, same features)"""
    z = np.load(f"{L.OUT}/dd1_{day}_s0.35_g1000.npz"); d = {k: z[k] for k in z.files}
    z0 = np.load(f"{L.OUT}/dd1_{day}.npz", mmap_mode="r")
    assert np.array_equal(d["k"], z0["k"]), f"{day}: rows differ from dd1_{day}.npz"
    bt = d["bt"].astype(np.int64); ok = bt > 0
    if (~ok).any():
        a = np.polyfit(d["s"][ok].astype(float), bt[ok].astype(float), 1); bt = np.where(ok, bt, np.round(np.polyval(a, d["s"].astype(float))).astype(np.int64))
    d["t"] = bt
    a, b = L.WIN[day]; m = (d["t"] >= L.pk(a)) & (d["t"] < L.pk(b))
    d = {k: v[m] for k, v in d.items()}
    d["day"] = day
    d["Xall"] = np.concatenate([d["F"], d["X"], d["f1"][:, None]], 1).astype(np.float32)
    X = d["Xall"]; f = lambda k: X[:, L.FNI[k]]
    d["env"] = (f("age_s") <= 343.67) & (f("drop_pct") >= 4.65) & (f("since_buy_s") <= 3.869) & (f("sol") >= 1.08)
    d["order"] = np.argsort(d["arr"], kind="stable")
    d["st_ng"] = d["st"].copy()
    return d

def with_guard(d, g):
    e = dict(d)
    e["st"] = np.where(d["st_ng"] == 2, 2, np.where(d["ratio"] <= g, 0, 1)).astype(np.int8)
    return e

def main():
    B0 = json.load(open(BUNDLE)); cols = [L.FNI[f] for f in B0["fn"]]
    tot = {}; per_day = {}; hrs = 0.0
    for day in DAYS:
        d = load_ng(day); h = (d["t"].max() - d["t"].min()) / 3600.0; hrs += h
        P, B = D20.bundle_scores(BUNDLE, d["Xall"][:, cols]); MIN = float(B["thr_default"])
        picks = {"IMIT1 top4 (Amsterdam)": d["env"] & (d["f1"] >= L.THR["top4"]), "M2 (Frankfurt gate)": d["env"] & (P >= MIN)}
        # how far the price has moved where our buy lands, on the picks (35 / 50 / 75 ms)
        for pn, sel in picks.items():
            r = d["ratio"][sel & (d["st_ng"][:, 0] != 2)]
            if len(r):
                per_day.setdefault((pn, "ratio"), []).append(r)
        for pn, sel in picks.items():
            for en, ex in EXITS:
                for g in GUARDS:
                    o = [L.sim(with_guard(d, g), sel, li, ex) for li in range(3)]
                    key = (pn, en, g)
                    acc = tot.setdefault(key, [[0.0, 0, 0] for _ in range(3)])
                    for li in range(3):
                        acc[li][0] += o[li]["pnl"]; acc[li][1] += o[li]["fill"]; acc[li][2] += o[li]["att"]
                    per_day.setdefault(key, {})[day] = [o[li]["pnl"] for li in range(3)]
        print(f"{day}: {h:.1f} h done", flush=True)
    print(f"\nGUARD SWEEP, days {' '.join(DAYS)} ({hrs:.1f} h), 0.35 SOL, all costs, FRA + AMS near leaders. SOL total (fills/attempts) at 35 / 50 / 75 ms landing")
    for pn in ("IMIT1 top4 (Amsterdam)", "M2 (Frankfurt gate)"):
        r = np.concatenate(per_day[(pn, "ratio")]); r35 = r[:, 0]
        print(f"\n== {pn}: price where our buy lands vs right after the dump (35 ms row): <=1.05 {np.mean(r35 <= 1.05):.0%}, 1.05-1.10 {np.mean((r35 > 1.05) & (r35 <= 1.10)):.0%}, "
              f"1.10-1.20 {np.mean((r35 > 1.10) & (r35 <= 1.20)):.0%}, >1.20 {np.mean(r35 > 1.20):.0%}")
        for en, _ in EXITS:
            print(f"  exit {en}")
            for g in GUARDS:
                a = tot[(pn, en, g)]; gl = "none" if g > 100 else f"+{(g - 1) * 100:.0f}%"
                days = "  by day @50: " + " ".join(f"{dy} {per_day[(pn, en, g)][dy][1]:+.2f}" for dy in DAYS)
                print(f"    guard {gl:>5}: " + " | ".join(f"{a[li][0]:+6.2f} ({a[li][1]}/{a[li][2]})" for li in range(3)) + days)

if __name__ == "__main__":
    main()
