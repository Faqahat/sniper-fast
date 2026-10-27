#!/usr/bin/env python3
# Owner 10-25 ~17:00 PKT: "are the dumpers related to the dev?" -- the big-sample check (our live fills are only ~90).
# Read-only replay on the dipdetect study data (dd1_<day>.npz, R1-R4 = 61 h, 0.55 SOL, +5% guard, all costs, one position per
# server, near-leader slots; dd_lib.sim). Every dump row carries the SELLER's wallet type (strategies/patterns/p1_build.py):
#   creator (the create signer / creator), insider (bought in the create slot), fresh (first trade < ~10 min before),
#   bot / family F1-F10 (R2-only lists), other.
# 1) the picks the bot actually takes (IMIT1 top4 = Amsterdam, M2 gate = Frankfurt; exit c4 = today's 5-slot hold, no stop),
#    split by who sold the dump, at 35 / 50 / 75 ms landing;
# 2) the same with creator + insider dumps skipped (does a "who dumped" filter add money?), per day.
# usage: python3 replay_seller_type.py [days...]
import sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect")
import json
import dd_lib as L
import dd20_shadow_eval as D20
DAYS = sys.argv[1:] or ["R1", "R2", "R3", "R4"]
BUNDLE = f"{L.OUT}/m2_v3_reg4_top25.json"
EX = L.EXI["c4_tpnone_slnone"]
def wname(w):
    w = int(w)
    return {0: "other", 1: "creator", 2: "insider (create slot)", 3: "fresh (< 10 min)", 4: "bot (list)"}.get(w, "family F1-F10" if w >= 11 else str(w))
B0 = json.load(open(BUNDLE)); cols = [L.FNI[f] for f in B0["fn"]]
by = collections.defaultdict(lambda: [[0, 0, 0.0, 0] for _ in range(3)])    # (pickset, type) -> per lat [att, fills, pnl, wins]
filt = collections.defaultdict(lambda: collections.defaultdict(lambda: [0.0, 0.0]))   # pickset -> day -> [base pnl@lat1, filtered pnl@lat1]
filt_all = collections.defaultdict(lambda: [[0.0, 0.0] for _ in range(3)])
hrs = 0.0
for day in DAYS:
    d = L.load(day); hrs += L.hours(d)
    P, B = D20.bundle_scores(BUNDLE, d["Xall"][:, cols]); MIN = float(B["thr_default"])
    wt = L.feat(d, "wt").astype(int)
    bad = (wt == 1) | (wt == 2)
    picks = {"IMIT1 top4": d["env"] & (d["f1"] >= L.THR["top4"]), "M2 gate": d["env"] & (P >= MIN), "every envelope dump": d["env"]}
    for pn, sel in picks.items():
        for li in range(3):
            o = L.sim(d, sel, li, EX, detail=True)
            for r, sv, p, filled in o["rows"]:
                a = by[(pn, wname(wt[r]))][li]; a[0] += 1; a[1] += filled; a[2] += p; a[3] += (p > 0 and filled)
            o2 = L.sim(d, sel & ~bad, li, EX)
            filt_all[pn][li][0] += o["pnl"]; filt_all[pn][li][1] += o2["pnl"]
            if li == 1: filt[pn][day] = [o["pnl"], o2["pnl"]]
    print(f"{day}: {L.hours(d):.1f} h", flush=True)
print(f"\nREPLAY {' '.join(DAYS)} ({hrs:.1f} h), 0.55 SOL, +5% guard, 5-slot hold no stop, all costs, near leaders, one position per server.")
print("Note: IMIT1 was fit before 10-23 06:00 (R1 + early R2 in-sample); bot/family lists are from R2.")
for pn in ("IMIT1 top4", "M2 gate", "every envelope dump"):
    print(f"\n== {pn}: by who sold the dump -> attempts, fills, SOL at 35 / 50 / 75 ms (per fill @50)")
    rows = sorted({k[1] for k in by if k[0] == pn}, key=lambda t: -by[(pn, t)][1][0])
    for t in rows:
        a = by[(pn, t)]
        print(f"   {t:<22} att {a[1][0]:5d}  fills {a[1][1]:5d}  " + " | ".join(f"{a[li][2]:+7.2f}" for li in range(3))
              + f"   per fill @50 {a[1][2] / max(a[1][1], 1):+.4f}  win {a[1][3] / max(a[1][1], 1):.0%}")
    f = filt_all[pn]
    print(f"   SKIP creator + insider dumps: " + " | ".join(f"{f[li][0]:+.2f} -> {f[li][1]:+.2f}" for li in range(3))
          + "   by day @50: " + " ".join(f"{dy} {filt[pn][dy][0]:+.2f}->{filt[pn][dy][1]:+.2f}" for dy in DAYS))
