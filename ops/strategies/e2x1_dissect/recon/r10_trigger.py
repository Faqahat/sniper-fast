#!/usr/bin/env python3
"""recon step 10 (read-only): size code + trigger trade per lot.
MEASURED: his buy SOL (exact mSOL) = round(f x vsol_after(T) , 1 mSOL) for one trade T shortly before his buy, f in {0.7%, 1.0%, 1.3%, 1.5%},
capped at 1.000 SOL. T = the latest trade (within 60 trades / 5 slots before his buy) that satisfies the equation for a tier f.
Out: trig.pkl {lot_id: dict(tier, trig_*)}; prints tier counts and the chance rate (same test with off-grid f = tier +- 0.0003)."""
import pickle, collections, numpy as np
H = "E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb"
OUT = "/home/moiz/sniper-data/e2x1_dissect/recon"
TIERS = [0.007, 0.010, 0.013, 0.015]
L = pickle.load(open(f"{OUT}/lots.pkl", "rb")); Z = pickle.load(open(f"{OUT}/tape.pkl", "rb"))
def match(l, t, k, fs):
    cm = round(l["cost"] * 1000); best = None
    for n in range(k - 1, max(-1, k - 61), -1):
        x = t[n]
        if x[0] < l["s"] - 5: break
        for f in fs:
            if round(f * x[9] / 1e6) == cm: return f, n
    return None, None
R = {}; chance = collections.Counter()
for l in L:
    t = [x for x in Z["trades"].get(l["mint"], []) if x[16]]
    k = next((n for n, x in enumerate(t) if x[15] == l["buy_sig"]), None)
    if k is None: R[l["lot_id"]] = dict(tier="?"); continue
    f, n = match(l, t, k, TIERS)
    for d in (-0.0003, 0.0003):
        g, _ = match(l, t, k, [round(x + d, 4) for x in TIERS]); chance[d] += g is not None
    if f is None:
        tier = "cap1" if abs(l["cost"] - 1.0) < 1e-9 else "none"
        R[l["lot_id"]] = dict(tier=tier); continue
    x = t[n]
    same = [y for y in t[n + 1:k] if y[4] != H]
    R[l["lot_id"]] = dict(tier=f"{f * 100:.1f}%", trig_slot_gap=l["s"] - x[0], trig_idx_gap=(l["i"] - x[1]) if x[0] == l["s"] else None, trig_buy=x[6],
                          trig_sol=x[7] / 1e9, trig_user=x[4], trig_signer=x[5], trig_relay=x[13], trig_sig=x[15], trig_vsol=x[9] / 1e9, trig_self=(x[4] == H),
                          n_between=len(same), sol_between_buy=sum(y[7] for y in same if y[6]) / 1e9, sol_between_sell=sum(y[7] for y in same if not y[6]) / 1e9)
pickle.dump(R, open(f"{OUT}/trig.pkl", "wb"))
W = [l for l in L if l["day"] in ("D0", "D1")]
print("tiers (D0+D1):", collections.Counter(R[l["lot_id"]]["tier"] for l in W).most_common())
print("chance matches with off-grid f (+-0.0003):", dict(chance), "of", len(L))
m = [R[l["lot_id"]] for l in W if "trig_slot_gap" in R[l["lot_id"]]]
print("trigger slot gap:", collections.Counter(min(r["trig_slot_gap"], 5) for r in m))
print("trigger side buy:", collections.Counter(r["trig_buy"] for r in m), "self:", sum(r["trig_self"] for r in m))
print("trigger sol p10/50/90:", np.percentile([r["trig_sol"] for r in m], [10, 25, 50, 75, 90]).round(3))
print("trades between trigger and his buy:", np.percentile([r["n_between"] for r in m], [10, 50, 90]))
