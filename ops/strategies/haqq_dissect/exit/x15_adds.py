#!/usr/bin/env python3
"""EXIT step 15 (read-only): haqq's pieces and adds (MEASURED on the tape 10-22 03:07 -> 10-28 01:12 PKT, non-DEAD positions).
 * how his sells map to lots (a sell = exactly one open lot's tokens within 1%, all open lots, or another piece)
 * which lot goes first when several are open (oldest / newest / middle)
 * single-lot positions sold in >1 piece: first piece size, gap, P&L vs one-piece
 * positions with adds vs without: count, P&L, holds, first-lot exit relative to the adds, add price vs first entry, per day
Out: haqq_dissect/exit/x15.txt"""
import pickle, sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
import xlib as X
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
Z = pickle.load(open(f"{X.OUT}/haqq.pkl", "rb")); L = Z["lots"]; S = Z["sells"]; POS = Z["pos"]
POS = [p for p in POS if p["close_cc"] is not None and L[p["lots"][0]]["t"] != "DEAD"]
P("# haqq's pieces and adds, non-DEAD closed positions (MEASURED)")
P(f"positions {len(POS):,}; with adds {sum(p['nb'] > 1 for p in POS):,} ({100 * np.mean([p['nb'] > 1 for p in POS]):.0f}%)")
ss = [S[i] for p in POS for i in p["sells"]]
P(f"sells {len(ss):,}: closes exactly one open lot (tokens within 1%) {100 * np.mean([s['matched'] for s in ss]):.1f}%")
mo = [s for s in ss if s["matched"] and s.get("lot_n_open", 1) >= 2]
c = collections.Counter("oldest" if s["lot_pos_in_open"] == 0 else "newest" if s["lot_pos_in_open"] == s["lot_n_open"] - 1 else "middle" for s in mo)
P(f"with >= 2 lots open ({len(mo):,} matched sells): oldest lot {c['oldest']:,} ({100 * c['oldest'] / len(mo):.0f}%), newest {c['newest']:,} ({100 * c['newest'] / len(mo):.0f}%), middle {c['middle']:,}")
# lots sold in more than one piece
nl = [l for p in POS for l in (L[i] for i in p["lots"])]
P(f"lots {len(nl):,}: closed by one sell {100 * np.mean([len(l['sells']) == 1 for l in nl]):.1f}%, by 2+ sells {100 * np.mean([len(l['sells']) >= 2 for l in nl]):.1f}%")
one = [p for p in POS if p["nb"] == 1]
mp = [p for p in one if p["ns"] >= 2]
P(f"\n## single-lot positions ({len(one):,}): sold in 2+ pieces {len(mp):,} ({100 * len(mp) / len(one):.1f}%)")
if mp:
    f1 = [S[p["sells"][0]]["frac"] for p in mp]; gap = [S[p["sells"][1]]["cc"] - S[p["sells"][0]]["cc"] for p in mp]
    r1 = [S[p["sells"][0]]["pos_ret"] for p in mp]
    P(f"- first piece fraction p25/50/75: {np.percentile(f1, [25, 50, 75]).round(2)}; ms to the next piece p25/50/75: {np.percentile(gap, [25, 50, 75]).round()}")
    P(f"- position return at the first piece p25/50/75: {np.percentile(r1, [25, 50, 75]).round(3)} (one-piece exits: {np.percentile([S[p['sells'][0]]['pos_ret'] for p in one if p['ns'] == 1], [25, 50, 75]).round(3)})")
    P(f"- P&L per position: multi-piece {1000 * np.mean([p['pnl'] for p in mp]):+.1f} mSOL (n {len(mp)}), one-piece {1000 * np.mean([p['pnl'] for p in one if p['ns'] == 1]):+.1f} (n {sum(p['ns'] == 1 for p in one)})")
P("\n## positions with adds vs without, per day (P&L SOL, curve, tx costs excluded)")
P("| day | no-add positions | P&L | mSOL/pos | with-add positions | P&L | mSOL/pos | buys/pos (adds) | first-lot P&L in add positions | add-lot P&L |")
P("|---|---|---|---|---|---|---|---|---|---|")
for d in range(7):
    a = [p for p in POS if p["day"] == d and p["nb"] == 1]; b = [p for p in POS if p["day"] == d and p["nb"] > 1]
    if not a: continue
    fl = sum(L[p["lots"][0]]["pnl"] for p in b); al = sum(L[i]["pnl"] for p in b for i in p["lots"][1:])
    P(f"| D{d} | {len(a):,} | {sum(p['pnl'] for p in a):+.1f} | {1000 * np.mean([p['pnl'] for p in a]):+.1f} | {len(b):,} | {sum(p['pnl'] for p in b):+.1f} | {1000 * np.mean([p['pnl'] for p in b]):+.1f} | {np.mean([p['nb'] for p in b]):.2f} | {fl:+.1f} | {al:+.1f} |")
b = [p for p in POS if p["nb"] > 1]
# add price vs first entry, time between buys, first lot sold before/after the adds
rel = []; dt = []; first_before = 0; first_after_last = 0; holds_first = []; holds_first_noadd = []
for p in b:
    l0 = L[p["lots"][0]]; px0 = l0["cost"] / l0["tok"]
    for i in p["lots"][1:]:
        li = L[i]; rel.append(li["cost"] / li["tok"] / px0 - 1); dt.append(li["cc"] - l0["cc"])
    last_add = L[p["lots"][-1]]["cc"]
    if l0["close_cc"] is not None and l0["close_cc"] < L[p["lots"][1]]["cc"]: first_before += 1
    if l0["close_cc"] is not None and l0["close_cc"] >= last_add: first_after_last += 1
    if l0["hold_ms"] is not None: holds_first.append(l0["hold_ms"])
for p in POS:
    if p["nb"] == 1 and L[p["lots"][0]]["hold_ms"] is not None: holds_first_noadd.append(L[p["lots"][0]]["hold_ms"])
P(f"\n- add price vs the first lot's price p10/25/50/75/90: {np.percentile(rel, [10, 25, 50, 75, 90]).round(3)} (share of adds BELOW the first price {100 * np.mean(np.array(rel) < 0):.0f}%)")
P(f"- ms from the first buy to an add p10/25/50/75/90: {np.percentile(dt, [10, 25, 50, 75, 90]).round()}")
P(f"- first lot already sold before the first add: {100 * first_before / len(b):.0f}% (a re-buy while still holding nothing of lot 1 is not an add); first lot held until after the last add: {100 * first_after_last / len(b):.0f}%")
P(f"- first-lot hold ms p25/50/75: with adds {np.percentile(holds_first, [25, 50, 75]).round()}, without adds {np.percentile(holds_first_noadd, [25, 50, 75]).round()}")
open(f"{X.OUT}/x15.txt", "w").write("\n".join(out) + "\n")
