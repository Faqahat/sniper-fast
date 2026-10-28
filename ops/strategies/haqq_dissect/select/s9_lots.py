#!/usr/bin/env python3
"""SELECT step 9 (read-only): bots 247/248's OWN lots (MEASURED, code-matched pos/p1.pkl, net after his costs) split by WHO dumped before
the buy: the trigger = the latest envelope sell on that mint within 0..2 slots before the buy (env.npz). Groups: seller is a serial launcher
(creates before the dump >= 20 / 5-19 / 2-4 / 1 = first-time dev / 0 = not a creator), dev or not; per day net and mSOL/lot, 90 % bootstrap.
Out: select/s9.txt"""
import sys, pickle, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
from plib import load, boot_sum
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/select"


def main():
    B, LO, _ = load(); ids, idm = L.ids_map()
    Z = np.load(f"{OUT}/env.npz"); A = {k: Z[k] for k in ("m", "s", "i", "f_sel_ncreates", "f_sel_dev", "f_sel_bal", "f_age_s", "sel")}
    key = A["m"].astype(np.int64) * 10**12 + A["s"].astype(np.int64) * 10**3 % 10**12 * 0 + 0
    # index env by mint -> arrays
    o = np.lexsort((A["i"], A["s"], A["m"])); m_ = A["m"][o].astype(np.int64); s_ = A["s"][o].astype(np.int64); i_ = A["i"][o].astype(np.int64)
    rows = []
    for l in LO:
        if l.get("code") not in (247, 248) or l["probe"]: continue
        b = B[l["b"]]; m = idm.get(l["mint"])
        if m is None: continue
        lo = np.searchsorted(m_, m); hi = np.searchsorted(m_, m, side="right")
        if hi == lo: g = "no envelope sell"; ncr = -1; dev = False
        else:
            ss = s_[lo:hi]; ii = i_[lo:hi]
            before = ((ss < b["slot"]) | ((ss == b["slot"]) & (ii < b["idx"]))) & (ss >= b["slot"] - 2)
            if not before.any(): g = "no envelope sell <= 2 slots"; ncr = -1; dev = False
            else:
                k = o[lo + np.flatnonzero(before)[-1]]
                ncr = int(A["f_sel_ncreates"][k]); dev = bool(A["f_sel_dev"][k] > 0.5)
                g = ("dev " if dev else "non-dev ") + ("creates>=20" if ncr >= 20 else "creates 5-19" if ncr >= 5 else "creates 2-4" if ncr >= 2 else "first-time dev" if ncr == 1 else "not a creator")
        rows.append((l["code"], l["day"], g, l["cnet"]))
    out = []
    def P(*a):
        s = " ".join(str(x) for x in a); print(s, flush=True); out.append(s)
    for code in (247, 248, "both"):
        R = [r for r in rows if code == "both" or r[0] == code]
        P(f"\n## bot {code}: {len(R):,} lots, net {sum(r[3] for r in R):+.1f} SOL (D0-D6)")
        P("| trigger seller | lots | share | net SOL [90%] | mSOL/lot | " + " | ".join(f"D{d}" for d in range(7)) + " | days > 0 |"); P("|---|---|---|---|---|" + "---|" * 7 + "---|")
        groups = sorted(set(r[2] for r in R), key=lambda g: -sum(r[3] for r in R if r[2] == g))
        for g in groups:
            v = np.array([r[3] for r in R if r[2] == g]); lo_, hi_ = boot_sum(v)
            pdays = [sum(r[3] for r in R if r[2] == g and r[1] == d) for d in range(7)]
            P(f"| {g} | {len(v):,} | {len(v) / len(R):.2f} | {v.sum():+.1f} [{lo_:+.1f}..{hi_:+.1f}] | {1000 * v.mean():+.1f} | " + " | ".join(f"{x:+.1f}" for x in pdays) + f" | {sum(x > 0 for x in pdays[:6])}/6 |")
    open(f"{OUT}/s9.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
