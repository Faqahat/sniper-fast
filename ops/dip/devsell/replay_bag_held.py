#!/usr/bin/env python3
# Owner 10-25 ~17:15 PKT follow-up to "are the dumpers related to the dev?": live losers had the creator / its wallets selling
# DURING our hold 13/58 vs winners 3/54. Can we see that risk at entry? Read-only replay (same data / sim as replay_seller_type.py):
# split the picks by how much of its bag the CREATOR (dev_sold) and the create-slot INSIDERS (ins_sold) had sold by the dump
# (p1_build.py: sold tokens / bought tokens so far, 0 when nothing bought or nothing sold), and test skipping "bag still held".
import sys, json, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect")
import dd_lib as L
import dd20_shadow_eval as D20
DAYS = sys.argv[1:] or ["R1", "R2", "R3", "R4"]
BUNDLE = f"{L.OUT}/m2_v3_reg4_top25.json"; EX = L.EXI["c4_tpnone_slnone"]
B0 = json.load(open(BUNDLE)); cols = [L.FNI[f] for f in B0["fn"]]
def bin_(x): return "sold none (or no bag)" if x <= 0 else "sold part" if x < 0.99 else "sold all"
by = collections.defaultdict(lambda: [[0, 0.0] for _ in range(3)])
tests = collections.defaultdict(lambda: [[0.0, 0] for _ in range(3)])
for day in DAYS:
    d = L.load(day)
    P, B = D20.bundle_scores(BUNDLE, d["Xall"][:, cols]); MIN = float(B["thr_default"])
    ds = L.feat(d, "dev_sold"); ins = L.feat(d, "ins_sold"); wt = L.feat(d, "wt").astype(int); bun = L.feat(d, "bundle_sol")
    picks = {"IMIT1 top4": d["env"] & (d["f1"] >= L.THR["top4"]), "M2 gate": d["env"] & (P >= MIN)}
    skips = {"none": np.zeros(len(ds), bool),
             "creator sold part (still holds some)": (ds > 0) & (ds < 0.99),
             "creator sold none + dump not by creator": (ds <= 0) & (wt != 1),
             "insiders sold part": (ins > 0) & (ins < 0.99) & (bun > 0)}
    for pn, sel in picks.items():
        for li in range(3):
            o = L.sim(d, sel, li, EX, detail=True)
            for r, sv, p, filled in o["rows"]:
                if not filled: continue
                for key in (("creator", bin_(ds[r])), ("insiders", bin_(ins[r]) if bun[r] > 0 else "no create-slot buys")):
                    a = by[(pn,) + key][li]; a[0] += 1; a[1] += p
            for sn, m in skips.items():
                o2 = L.sim(d, sel & ~m, li, EX); t = tests[(pn, sn)][li]; t[0] += o2["pnl"]; t[1] += o2["fill"]
    print(day, "done", flush=True)
for pn in ("IMIT1 top4", "M2 gate"):
    print(f"\n== {pn} (fills, SOL at 35 / 50 / 75 ms, per fill @50)")
    for who in ("creator", "insiders"):
        for b in sorted({k[2] for k in by if k[0] == pn and k[1] == who}):
            a = by[(pn, who, b)]
            print(f"   {who:<8} {b:<24} fills {a[1][0]:5d}  " + " | ".join(f"{a[li][1]:+7.2f}" for li in range(3)) + f"   {a[1][1] / max(a[1][0], 1):+.4f}/fill")
    print("   skip test (SOL at 35 / 50 / 75 ms):")
    for sn in ("none", "creator sold part (still holds some)", "creator sold none + dump not by creator", "insiders sold part"):
        t = tests[(pn, sn)]
        print(f"      skip {sn:<42} " + " | ".join(f"{t[li][0]:+7.2f} ({t[li][1]})" for li in range(3)))
