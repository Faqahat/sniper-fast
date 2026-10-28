#!/usr/bin/env python3
"""recon step 4 (read-only): FIFO lot table per mint from the per-tx table (tx.pkl, + RPC-only txs from rpc_tx.pkl if present).
Lot = one successful buy. A sell takes tokens FIFO from the open lots of its mint; its net SOL (pump: sol - fee - cfee from the
TradeEvent; PumpSwap: wallet delta + txfee + tips - rent recovered) and its txfee + tips are split pro rata by tokens taken.
Rent: the buy's created token account (rent_c) is a lot cost; rent recovered on the closing sell (rent_x) is split like proceeds.
Buy 'curve_extend' (other lamports paid to the curve beyond the TradeEvent, 650,240 = 128 B rent) is a lot cost.
Failed txs: fee attached to the lot that is open on that mint at that time (else the next lot on the mint within 120 s, else 'orphan').
Out: /home/moiz/sniper-data/e2x1_dissect/recon/lots.pkl (list of dicts, one per lot; no pandas on this host) + fails.pkl"""
import pickle, collections, os, sys, json
import numpy as np
H = "E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb"
OUT = "/home/moiz/sniper-data/e2x1_dissect/recon"
W0 = 1793113200; W1 = W0 + 86400; WA = W0 - 86400
rows = pickle.load(open(f"{OUT}/tx.pkl", "rb"))
if os.path.exists(f"{OUT}/rpc_tx.pkl"):
    have = {r["sig"] for r in rows}
    rows += [r for r in pickle.load(open(f"{OUT}/rpc_tx.pkl", "rb")) if r["sig"] not in have]
rows.sort(key=lambda r: (r["s"], r["i"] if r["i"] is not None else 0))
def htok(r):        # his token delta on the mint from tb (owner == H)
    for m, o, a, b in (r.get("tb") or []):
        if o == H and m == r["mint"]: return b - a
    return None
bym = collections.defaultdict(list)
for r in rows:
    if r["own"] and r["ok"] and r["kind"] in ("buy", "sell"): bym[r["mint"]].append(r)
LOTS = []; UNM = []
for mint, lst in bym.items():
    q = []
    for r in lst:
        if r["kind"] == "buy":
            e = r["events"][0] if r["events"] else None
            tok = e["tok"] if e else htok(r)
            cost = -r["trade"]
            pre_vsol = e["vsol"] - e["sol"] if e else None          # curve virtual SOL before his buy
            lot = dict(lot_id=len(LOTS), mint=mint, buy_sig=r["sig"], s=r["s"], i=r["i"], bt=r["bt"], tok=tok, left=float(tok), cost=cost / 1e9,
                       sol_curve=(e["sol"] if e else 0) / 1e9, pfee=(e["fee"] if e else 0) / 1e9, cfee=(e["cfee"] if e else 0) / 1e9,
                       buy_txfee=r["txfee"] / 1e9, buy_tip=r["tips"] / 1e9, buy_relay=r["relay"], buy_tip_amt=(r["tip_amt"][0] if r["tip_amt"] else 0),
                       buy_cup=r["cup"], buy_cul=r["cul"], buy_cu=r["cu"], rent_c=r["rent_c"] / 1e9, curve_extend=-r["other"] / 1e9,
                       vsol_after=(e["vsol"] / 1e9 if e else None), vtok_after=(e["vtok"] if e else None), vsol_before=(pre_vsol / 1e9 if e else None),
                       creator=(e["creator"] if e else None), fbps=(e["fbps"] if e else None), cbps=(e["cbps"] if e else None),
                       proceeds=0.0, sell_txfee=0.0, sell_tip=0.0, rent_x=0.0, sells=[], n_sells=0, close_s=None, close_i=None, close_bt=None,
                       sell_relays=set(), sell_tip_amts=set(), sell_culs=set(), swap_sell=False, fail_fee=0.0, n_fail=0, n_fail_sell=0, n_fail_buy=0)
            LOTS.append(lot); q.append(lot)
        else:
            if r["events"]:
                e = r["events"][0]; T = float(e["tok"]); Pn = r["trade"] / 1e9; swap = False
            else:
                d = htok(r); T = float(-d) if d else 0.0; swap = True
                Pn = (r["sd"] + r["txfee"] + r["tips"] - r["rent_x"]) / 1e9
            C_fee = r["txfee"] / 1e9; C_tip = r["tips"] / 1e9; RX = r["rent_x"] / 1e9
            need = T; taken = []
            for l in list(q):
                if need <= 0.5: break
                take = min(l["left"], need); taken.append((l, take)); l["left"] -= take; need -= take
                if l["left"] <= 0.5: l["left"] = 0.0; q.remove(l); l["close_s"] = r["s"]; l["close_i"] = r["i"]; l["close_bt"] = r["bt"]
            tot = sum(t for _, t in taken)
            for l, take in taken:
                f = take / T if T > 0 else 0
                l["proceeds"] += Pn * f; l["sell_txfee"] += C_fee * f; l["sell_tip"] += C_tip * f
                l["sells"].append((r["sig"], r["s"], r["i"], r["bt"], take, Pn * f)); l["n_sells"] += 1
                l["sell_relays"].add(r["relay"]); l["sell_tip_amts"].add(r["tip_amt"][0] if r["tip_amt"] else 0); l["sell_culs"].add(r["cul"])
                if swap: l["swap_sell"] = True
            # rent recovered: to the lot(s) that this sell closed (account closed when position goes to 0)
            closed = [l for l, t in taken if l["left"] == 0.0]
            if RX and closed:
                for l in closed: l["rent_x"] += RX / len(closed)
            elif RX:
                UNM.append(dict(kind="rent_x_no_lot", sig=r["sig"], mint=mint, bt=r["bt"], sol=RX))
            if need > 0.5:
                UNM.append(dict(kind="sell_unmatched", sig=r["sig"], mint=mint, bt=r["bt"], tok=need, sol=(Pn - C_fee - C_tip) * need / T if T else 0, rent_x=RX if not taken else 0))
# failed txs -> lots
F = []
lots_by_m = collections.defaultdict(list)
for l in LOTS: lots_by_m[l["mint"]].append(l)
for r in rows:
    if not (r["own"] and not r["ok"]): continue
    fk = "sell" if "Sell" in r["ixn"] else "buy" if ("Buy" in r["ixn"] or r["cul"] == 145000) else "?"
    best = None
    for l in lots_by_m.get(r["mint"], []):
        cb = l["close_bt"] if l["close_bt"] is not None else 10**12
        if l["bt"] - 120 <= r["bt"] <= cb + 120: best = l if best is None or abs(l["bt"] - r["bt"]) < abs(best["bt"] - r["bt"]) else best
    F.append(dict(sig=r["sig"], s=r["s"], i=r["i"], bt=r["bt"], mint=r["mint"], fkind=fk, fee=r["txfee"] / 1e9, err=str(r["err"]), cul=r["cul"],
                  lot_id=best["lot_id"] if best else None))
    if best:
        best["fail_fee"] += r["txfee"] / 1e9; best["n_fail"] += 1; best["n_fail_" + ("sell" if fk == "sell" else "buy")] += 1
for l in LOTS:
    l["buy_costs"] = l["buy_txfee"] + l["buy_tip"] + l["curve_extend"]
    l["open_tok"] = l["left"]; l["is_open"] = l["left"] > 0.5
    l["hold_s"] = (l["close_bt"] - l["bt"]) if l["close_bt"] is not None else None
    l["hold_slots"] = (l["close_s"] - l["s"]) if l["close_s"] is not None else None
    l["first_sell_slots"] = (l["sells"][0][1] - l["s"]) if l["sells"] else None
    l["pnl_cash"] = l["proceeds"] - l["cost"] - l["buy_costs"] - l["sell_txfee"] - l["sell_tip"] - l["rent_c"] + l["rent_x"] - l["fail_fee"]
    l["day"] = "D0" if WA <= l["bt"] < W0 else "D1" if W0 <= l["bt"] < W1 else ("pre" if l["bt"] < WA else "post")
    l["sell_relays"] = "+".join(sorted(l["sell_relays"])); l["sell_tip_amts"] = tuple(sorted(l["sell_tip_amts"])); l["sell_culs"] = tuple(sorted(x for x in l["sell_culs"] if x))
    l["gmgn"] = f"https://gmgn.ai/sol/token/{l['mint']}"; l["buy_tx"] = f"https://solscan.io/tx/{l['buy_sig']}"
pickle.dump(LOTS, open(f"{OUT}/lots.pkl", "wb"))
pickle.dump(dict(fails=F, unm=UNM), open(f"{OUT}/fails.pkl", "wb"))
print("lots", len(LOTS), collections.Counter(l["day"] for l in LOTS), "open", sum(l["is_open"] for l in LOTS), "unmatched", collections.Counter(u["kind"] for u in UNM))
print("fails", len(F), collections.Counter((f["fkind"], f["lot_id"] is not None) for f in F))
for d in ("D0", "D1"):
    x = [l for l in LOTS if l["day"] == d]; c = [l for l in x if not l["is_open"]]
    print(d, "lots", len(x), "closed", len(c), "pnl_cash(closed) %.4f" % sum(l["pnl_cash"] for l in c), "win %.0f%%" % (100 * np.mean([l["pnl_cash"] > 0 for l in c])),
          "hold p50 %s s" % np.median([l["hold_s"] for l in c]), "size p50 %.3f" % np.median([l["cost"] for l in x]))
