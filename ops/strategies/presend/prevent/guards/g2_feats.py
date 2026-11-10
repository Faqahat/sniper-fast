#!/usr/bin/env python3
"""GUARDS step 2 [MEASURED on the decoded chain tapes]: for every live fill, the chain state AT OUR LANDING POSITION (every trade with a
lower (slot, tx index) executed before our buy) and at the filled try's SIGNING position (the newest trade the engine had seen):
  whale (T2: trigger wallet; re-arm: the dump seller) balance at sign / at landing vs its trigger balance,
  holders >= 3% / >= 6% of supply at sign (not ours) and each one's balance at landing,
  who moved the price between signing and landing (sells, the biggest seller, whether it was the whale / a sign-time holder),
  what happened after our buy until our sell landed (sells by the whale / sign-time holders / anyone, SOL),
  whether the token's tape covers its history (first trade within 2 slots of the create).
Out: /home/it/sniper-data/prevent/guards/feats.pkl
usage: g2_feats.py"""
import pickle, sys, collections
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/prevent/guards")
import glib as G
OUT = "/home/it/sniper-data/prevent/guards"
F = pickle.load(open(f"{OUT}/fills.pkl", "rb"))
tapes = G.load_tapes({f["mint"] for f in F})
print("mints", len({f['mint'] for f in F}), "with tape", len(tapes), flush=True)
pickle.dump(tapes, open(f"{OUT}/tapes_fills.pkl", "wb"))
res = []
for f in F:
    rows = tapes.get(f["mint"])
    o = dict(f); o["tape"] = bool(rows)
    if not rows: res.append(o); continue
    H = G.Hold(rows)
    L = H.key(f["slot"], f["idx"], 0)
    sp = f["sign_pos"] or [f["slot"], 0, 0]
    S = H.key(sp[0], sp[1], sp[2]) + 1
    # history coverage: the first trade of the mint vs the trigger age
    o["hist_ok"] = H.first_slot is not None and f["age"] is not None and f["trig_slot"] is not None and H.first_slot >= f["trig_slot"] - f["age"] - 2
    # our tx is on the tape?
    o["ours_on_tape"] = any(r[0] == f["slot"] and r[1] == f["idx"] and r[8] in G.OURS for r in rows[max(0, __import__('bisect').bisect_left(H.keys, L) - 2):__import__('bisect').bisect_left(H.keys, L) + 3])
    wh = f["whale"]
    o["wh_S"] = H.bal_before(wh, S); o["wh_L"] = H.bal_before(wh, L)
    tb = f["trig_bal"] or 0
    if f["kind"] == "t2":
        # the trigger balance from the tape (after the trigger trade) as a cross-check of the engine's number
        kT = H.key(f["trig_slot"], f["trig_idx"], f["trig_j"]) + 1
        o["wh_T"] = H.bal_before(wh, kT)
    else:
        kT = H.key(f["trig_slot"], f["trig_idx"], f["trig_j"]) + 1
        o["wh_T"] = H.bal_before(wh, kT)
    for X in (0.03, 0.06):
        hs = H.holders_before(S, X)
        o[f"H{int(X*100)}_S"] = hs
        o[f"H{int(X*100)}_L"] = {u: H.bal_before(u, L) for u in hs}
    # all holders >= 3% at landing (what the chain had; incl. wallets the engine had not seen yet at signing)
    o["H3_Lall"] = H.holders_before(L, 0.03)
    # between signing and landing: who moved the price
    import bisect
    a = bisect.bisect_left(H.keys, S); b = bisect.bisect_left(H.keys, L)
    mid = [r for r in rows[a:b] if r[8] not in G.OURS]
    sells = collections.Counter()
    for r in mid:
        if not r[3]: sells[r[8]] += r[4]
    o["mid_sell_sol"] = sum(sells.values()) / 1e9; o["mid_buy_sol"] = sum(r[4] for r in mid if r[3]) / 1e9
    o["mid_top_seller"] = sells.most_common(1)[0][0] if sells else None
    o["mid_top_sol"] = sells.most_common(1)[0][1] / 1e9 if sells else 0.0
    o["mid_whale_sol"] = sells.get(wh, 0) / 1e9
    o["mid_H6_sol"] = sum(v for u, v in sells.items() if u in o["H6_S"]) / 1e9
    o["mid_H3_sol"] = sum(v for u, v in sells.items() if u in o["H3_S"]) / 1e9
    # after our buy until our sell landed (else fill slot + 2)
    c = f.get("close") or {}
    sl = c.get("sell_land") or (f["sells"][0] if f["sells"] else None)
    E = H.key(sl[0], sl[1], 0) if sl else H.key(f["slot"] + 2, 10 ** 5, 0)
    e = bisect.bisect_left(H.keys, E)
    aft = [r for r in rows[b:e] if r[8] not in G.OURS]
    s2 = collections.Counter()
    for r in aft:
        if not r[3]: s2[r[8]] += r[4]
    o["aft_sell_sol"] = sum(s2.values()) / 1e9; o["aft_buy_sol"] = sum(r[4] for r in aft if r[3]) / 1e9
    o["aft_whale_sol"] = s2.get(wh, 0) / 1e9
    o["aft_H6_sol"] = sum(v for u, v in s2.items() if u in o["H6_S"]) / 1e9
    o["aft_H3_sol"] = sum(v for u, v in s2.items() if u in o["H3_S"]) / 1e9
    o["aft_H3L_sol"] = sum(v for u, v in s2.items() if u in o["H3_Lall"]) / 1e9
    o["aft_top_seller"] = s2.most_common(1)[0][0] if s2 else None
    o["aft_top_sol"] = s2.most_common(1)[0][1] / 1e9 if s2 else 0.0
    # the same slot / next slot split of the whale's and holders' after-sells
    o["aft_same_slot_H3"] = sum(r[4] for r in aft if not r[3] and r[0] == f["slot"] and r[8] in o["H3_S"]) / 1e9
    o["sell_land"] = sl
    res.append(o)
pickle.dump(res, open(f"{OUT}/feats.pkl", "wb"))
print("fills", len(res), "with tape", sum(1 for o in res if o["tape"]), "hist_ok", sum(1 for o in res if o.get("hist_ok")), "ours_on_tape", sum(1 for o in res if o.get("ours_on_tape")))
c = collections.Counter((o["run"], o["tape"], o.get("ours_on_tape")) for o in res)
for k in sorted(c): print(k, c[k])
