#!/usr/bin/env python3
"""recon step 9 (read-only): per-lot entry context from the tape (tape.pkl): token age, curve state, what happened just before his buy
(same slot / previous slots), and whether his buy shares a slot with the trigger. Out: feat.pkl {lot_id: dict}"""
import pickle, collections, numpy as np
H = "E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb"
OUT = "/home/moiz/sniper-data/e2x1_dissect/recon"
Z = pickle.load(open(f"{OUT}/tape.pkl", "rb")); TR, CR = Z["trades"], Z["creates"]
LOTS = pickle.load(open(f"{OUT}/lots.pkl", "rb"))
F = {}
for l in LOTS:
    t = TR.get(l["mint"], []); c = CR.get(l["mint"])
    ok = [x for x in t if x[16]]
    # index of his buy
    k = next((n for n, x in enumerate(ok) if x[15] == l["buy_sig"]), None)
    f = dict(age_s=(l["bt"] - c["bt"]) if c else None, age_slots=(l["s"] - c["slot"]) if c else None, create_slot=c["slot"] if c else None,
             creator=c.get("creator") if c else None, mayhem=c.get("mayhem") if c else None, cashback=c.get("cashback") if c else None, holder=c.get("holder") if c else None, his_in_tape=k is not None)
    if k is not None:
        prev = ok[:k]
        others = [x for x in prev if x[4] != H]
        f["n_trades_before"] = len(others)
        f["n_buyers_before"] = len({x[4] for x in others if x[6]})
        same = [x for x in others if x[0] == l["s"]]
        f["same_slot_before"] = len(same)
        f["same_slot_buy_sol"] = sum(x[7] for x in same if x[6]) / 1e9; f["same_slot_sell_sol"] = sum(x[7] for x in same if not x[6]) / 1e9
        if others:
            p = others[-1]
            f.update(prev_slot_gap=l["s"] - p[0], prev_buy=p[6], prev_sol=p[7] / 1e9, prev_user=p[4], prev_signer=p[5], prev_relay=p[13], prev_sig=p[15],
                     prev_dt=l["bt"] - p[3])
        # flow in the last 10 slots before his buy (incl. same slot)
        w = [x for x in others if l["s"] - 10 <= x[0] <= l["s"]]
        f["buy10"] = sum(x[7] for x in w if x[6]) / 1e9; f["sell10"] = sum(x[7] for x in w if not x[6]) / 1e9
        f["max_buy10"] = max([x[7] for x in w if x[6]], default=0) / 1e9; f["max_sell10"] = max([x[7] for x in w if not x[6]], default=0) / 1e9
        # biggest trade in the 10 slots and its slot distance
        if w:
            b = max(w, key=lambda x: x[7]); f.update(big_sol=b[7] / 1e9, big_buy=b[6], big_gap=l["s"] - b[0], big_user=b[4])
        # peak vsol before his buy (since creation) and drawdown from peak
        if others:
            pk = max(x[9] for x in others); f["peak_vsol"] = pk / 1e9; f["dd_from_peak"] = l["vsol_before"] / (pk / 1e9) - 1 if l["vsol_before"] else None
        nxt = ok[k + 1:]
        f["n_after_same_slot"] = sum(1 for x in nxt if x[0] == l["s"])
    F[l["lot_id"]] = f
pickle.dump(F, open(f"{OUT}/feat.pkl", "wb"))
print("done", len(F), sum(1 for f in F.values() if f["his_in_tape"]))
