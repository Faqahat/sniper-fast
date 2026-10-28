#!/usr/bin/env python3
"""8yYMhu a2 (read-only): per successful buy (lots.pkl), the market tape around it: previous outside trade, the trigger = last outside
sell >= 1 SOL at or before his position (same slot: lower index), slot gap / index gap / trades in between, block positions, leader
client and location, seller history on the token (creator / create-slot buyer / early buyer / position share), token age and curve.
Out: DATA/buys.pkl (one dict per lot_id)"""
import sys, os, pickle, collections, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, rlib as X, tlib as T
L = pickle.load(open(f"{X.D}/lots.pkl", "rb"))
mints, users = T.names(); wid = T.uid()[X.W]
CR = json.load(open("/home/moiz/sniper-data/dv8/tab/creates.json"))
CR.update(json.load(open("/home/moiz/sniper-data/e2x1_dissect/select/creates_new.json")))
out = {}
bym = collections.defaultdict(list)
for l in L: bym[l["mint"]].append(l)
for mint, ls in bym.items():
    tr = T.trades(mint)
    if tr is None:
        for l in ls: out[l["lot_id"]] = dict(lot=l["lot_id"], tape=False)
        continue
    key = tr["slot"].astype(np.int64) * 4096 + tr["idx"].astype(np.int64)
    cr = CR.get(mint)
    if cr and cr.get("slot"): cslot, cuser, cbt = int(cr["slot"]), T.uid().get(cr.get("creator"), -1), int(cr.get("bt") or 0)
    elif (int(tr["vsol"][0]) - int(tr["sol"][0])) in (30000000000,) and tr["buy"][0]:
        cslot, cuser, cbt = int(tr["slot"][0]), int(tr["user"][0]), int(tr["bt"][0])
    else: cslot, cuser, cbt = None, -1, None
    for l in ls:
        k = int(l["s"]) * 4096 + int(l["i"])
        p = int(np.searchsorted(key, k))          # first row at/after his buy
        me = p if p < len(tr) and key[p] == k and tr["user"][p] == wid else None
        b = tr[:p]
        outside = b["user"] != wid
        r = dict(lot=l["lot_id"], tape=True, n_before=int(outside.sum()), me_on_tape=me is not None, cslot=cslot, creator=cuser,
                 age_slots=(int(l["s"]) - cslot) if cslot else None, age_s=(int(l["bt"]) - cbt) if cbt else None)
        ob = np.nonzero(outside)[0]
        if len(ob):
            q = ob[-1]; t = b[q]
            r.update(prev_slot=int(t["slot"]), prev_idx=int(t["idx"]), prev_buy=bool(t["buy"]), prev_sol=int(t["sol"]) / 1e9, prev_user=users[t["user"]],
                     prev_gap=int(l["s"]) - int(t["slot"]))
        sells = np.nonzero(outside & (b["buy"] == 0) & (b["sol"] >= 1_000_000_000))[0]
        if len(sells):
            q = sells[-1]; t = b[q]
            between = b[q + 1:]
            u = int(t["user"])
            # seller history on this token before the sell
            hist = b[:q]
            hu = hist[hist["user"] == u]
            bought = int(hu["tok"][hu["buy"] == 1].sum()); soldb = int(hu["tok"][hu["buy"] == 0].sum())
            first_buy_slot = int(hu["slot"][hu["buy"] == 1][0]) if (hu["buy"] == 1).any() else None
            nbuyers_before_first = None
            if first_buy_slot is not None:
                fb = np.nonzero((hist["user"] == u) & (hist["buy"] == 1))[0][0]
                nbuyers_before_first = len(set(hist["user"][:fb].tolist()))
            r.update(trig_slot=int(t["slot"]), trig_idx=int(t["idx"]), trig_j=int(t["j"]), trig_sol=int(t["sol"]) / 1e9, trig_tok=int(t["tok"]), trig_user=users[u], trig_uid=u,
                     trig_vsol_after=int(t["vsol"]) / 1e9, trig_vsol_before=(int(t["vsol"]) + int(t["sol"])) / 1e9, trig_gap=int(l["s"]) - int(t["slot"]),
                     trig_igap=(int(l["i"]) - int(t["idx"])) if int(l["s"]) == int(t["slot"]) else None, n_between=len(between),
                     n_between_buys=int((between["buy"] == 1).sum()), sol_between_buys=int(between["sol"][between["buy"] == 1].sum()) / 1e9,
                     sol_between_sells=int(between["sol"][between["buy"] == 0].sum()) / 1e9,
                     seller_is_creator=(u == cuser), seller_bought_tok=bought, seller_sold_before_tok=soldb, seller_first_buy_slot=first_buy_slot,
                     seller_create_slot_buyer=(first_buy_slot is not None and cslot is not None and first_buy_slot == cslot),
                     seller_nbuyers_before=nbuyers_before_first, seller_frac_sold=(int(t["tok"]) / bought if bought else None),
                     trig_bt=int(t["bt"]))
        # >=1 SOL outside sells in his slot (before / after him)
        sl = (tr["slot"] == l["s"]) & (tr["user"] != wid) & (tr["buy"] == 0) & (tr["sol"] >= 1_000_000_000)
        r["sell1_same_slot_before"] = int((sl & (key < k)).sum()); r["sell1_same_slot_any"] = int(sl.sum())
        r["sell1_prev_slot"] = int(((tr["slot"] == l["s"] - 1) & (tr["user"] != wid) & (tr["buy"] == 0) & (tr["sol"] >= 1_000_000_000)).sum())
        # peak vsol before, flow in last 10 slots
        if len(b):
            r["peak_vsol_before"] = int(b["vsol"].max()) / 1e9
            w10 = b[b["slot"] >= l["s"] - 10]
            r["buy10"] = int(w10["sol"][w10["buy"] == 1].sum()) / 1e9; r["sell10"] = int(w10["sol"][w10["buy"] == 0].sum()) / 1e9
            r["n_trades_before"] = len(b); r["n_users_before"] = len(set(b["user"].tolist()))
        out[l["lot_id"]] = r
for lid, r in out.items():
    l = L[lid]
    r["client"] = X.leader(l["s"])[1]; r["area"] = X.area(l["s"]); r["frac"] = X.frac(l["s"], l["i"]); r["bsize"] = X.bsize(l["s"])
    if r.get("trig_slot") is not None:
        r["trig_frac"] = X.frac(r["trig_slot"], r["trig_idx"]); r["trig_client"] = X.leader(r["trig_slot"])[1]
        r["ms"] = X.cc(l["s"], l["i"]) - X.cc(r["trig_slot"], r["trig_idx"])
pickle.dump(out, open(f"{X.D}/buys.pkl", "wb"))
print("buys", len(out), "on tape", sum(r["tape"] for r in out.values()), "me found", sum(r.get("me_on_tape", False) for r in out.values()),
      "with trigger", sum("trig_slot" in r for r in out.values()))
