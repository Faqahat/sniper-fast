#!/usr/bin/env python3
"""8yYMhu a3 (read-only): the ATTEMPT table = every buy order that reached the chain (landed buys + failed buy txs), each tied to its
trigger = the last outside sell >= 1 SOL on that mint at or before the attempt (6001 'late' failures: in the slot BEFORE, since their
deadline is the trigger slot -- MEASURED on the RPC sample). Outcome: landed / late (6001) / band (6401/6400) / slip (6002) / dup (Custom 0) / other.
Adds block positions, chain-clock ms, leader client + location, landed relay/tip, CU price. Out: DATA/att.pkl"""
import sys, os, pickle, collections, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, rlib as X, tlib as T
TX = pickle.load(open(f"{X.D}/tx.pkl", "rb"))
RP = pickle.load(open(f"{X.D}/rpc_tx.pkl", "rb")) if os.path.exists(f"{X.D}/rpc_tx.pkl") else []
have = {r["sig"] for r in TX}
rows = TX + [r for r in RP if r["sig"] not in have and r.get("why") == "missing"]
L = pickle.load(open(f"{X.D}/lots.pkl", "rb")); lot_by_buy = {l["buy_sig"]: l for l in L}
mints, users = T.names(); wid = T.uid()[X.W]
def outcome(r):
    if r["ok"]: return "landed"
    e = json.dumps(r["err"])
    if "6001" in e: return "late"
    if "6401" in e or "6400" in e: return "band"
    if "6002" in e: return "slip"
    if '"Custom": 0' in e: return "dup"
    return "other"
A = []
cache = {}
for r in rows:
    if not r["own"]: continue
    if r["ok"] and r["kind"] != "buy": continue
    if not r["ok"]:
        e = json.dumps(r["err"])
        if "Sell" in r["ixn"] or "3012" in e or "6003" in e: continue
    mint = r["mint"] if r["mint"] else (r.get("mints") or [None])[0]
    if mint is None: continue
    o = outcome(r)
    if mint not in cache: cache[mint] = T.trades(mint)
    tr = cache[mint]
    a = dict(sig=r["sig"], s=r["s"], i=r["i"], bt=r["bt"], mint=mint, out=o, relay=r["relay"], tip=r["tips"] if r["ok"] else None, tip_amt=r["tip_amt"],
             cup=r["cup"], cul=r["cul"], fee=r["txfee"], lot=(lot_by_buy[r["sig"]]["lot_id"] if r["sig"] in lot_by_buy else None))
    if tr is not None and r["i"] is not None:
        key = tr["slot"].astype(np.int64) * 4096 + tr["idx"].astype(np.int64)
        lim = (int(r["s"]) - (1 if o == "late" else 0)) * 4096 + (4095 if o == "late" else int(r["i"]))
        p = int(np.searchsorted(key, lim, side="right")) if o == "late" else int(np.searchsorted(key, lim))
        b = tr[:p]
        sel = np.nonzero((b["user"] != wid) & (b["buy"] == 0) & (b["sol"] >= 1_000_000_000))[0]
        if len(sel):
            t = b[sel[-1]]
            a.update(trig_slot=int(t["slot"]), trig_idx=int(t["idx"]), trig_sol=int(t["sol"]) / 1e9, trig_vsol_after=int(t["vsol"]) / 1e9, trig_user=users[t["user"]],
                     trig_gap=int(r["s"]) - int(t["slot"]), trig_frac=X.frac(t["slot"], t["idx"]), trig_bsize=X.bsize(t["slot"]))
            if a["trig_gap"] == 0: a["igap"] = int(r["i"]) - int(t["idx"])
            a["ms"] = X.cc(r["s"], r["i"]) - X.cc(t["slot"], t["idx"])
            # outside trades between the trigger and the attempt (exclusive), on this mint
            k0 = int(t["slot"]) * 4096 + int(t["idx"]); k1 = int(r["s"]) * 4096 + int(r["i"])
            bt_ = tr[(key > k0) & (key < k1) & (tr["user"] != wid)]
            a["n_between"] = len(bt_); a["buys_between"] = int((bt_["buy"] == 1).sum()); a["sol_buys_between"] = int(bt_["sol"][bt_["buy"] == 1].sum()) / 1e9
            a["first_between_user"] = users[bt_["user"][0]] if len(bt_) else None
            # the trigger slot's tail: last pump tx index seen in the trigger slot (block size proxy)
    a["client"] = X.leader(r["s"])[1]; a["area"] = X.area(r["s"]); a["frac"] = X.frac(r["s"], r["i"]) if r["i"] is not None else None
    if "trig_slot" in a: a["trig_client"] = X.leader(a["trig_slot"])[1]; a["trig_area"] = X.area(a["trig_slot"])
    A.append(a)
pickle.dump(A, open(f"{X.D}/att.pkl", "wb"))
c = collections.Counter(a["out"] for a in A)
print("attempts", len(A), dict(c), "with trigger", sum("trig_slot" in a for a in A))
