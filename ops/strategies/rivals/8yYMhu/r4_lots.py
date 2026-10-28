#!/usr/bin/env python3
"""8yYMhu step 4 (read-only): FIFO lot table per mint from tx.pkl (+ RPC rows rpc_tx.pkl for txs the recorder missed).
Lot = one successful buy. A sell takes tokens FIFO from open lots of its mint; its net SOL (pump TradeEvent: sol - fee - cfee;
non-pump sells: wallet delta + txfee + tips - rent back) and its txfee + tips are split pro rata by tokens taken.
Rent: the buy's token account (rent_c) is a lot cost; rent back on the closing sell (rent_x) goes to the lot(s) it closed.
Buy 'other' lamports (curve realloc etc.) are a lot cost. Failed txs: fee attached to the lot open on that mint at that time
(else the lot bought within +-30 s after it, else 'orphan' = an attempt that never filled).
Out: DATA/lots.pkl, DATA/fails.pkl"""
import pickle, collections, os, json
import numpy as np
W = "8yYMhuYo1LzgCmeeg3vRkhRtJ8xFC7v7S4ufABtQXjS3"
D = "/home/moiz/sniper-data/rivals/8yYMhu"
rows = pickle.load(open(f"{D}/tx.pkl", "rb"))
if os.path.exists(f"{D}/rpc_tx.pkl"):
    RP = {r["sig"]: r for r in pickle.load(open(f"{D}/rpc_tx.pkl", "rb"))}
    # recorder rows without a decodable TradeEvent (3 sells) -> use the RPC decode of the same tx
    rows = [RP[r["sig"]] if (r["sig"] in RP and r["own"] and r["ok"] and r["kind"] in ("buy", "sell") and not r["events"] and RP[r["sig"]]["events"]) else r for r in rows]
    have = {r["sig"] for r in rows}
    rows += [r for r in RP.values() if r["sig"] not in have]
rows.sort(key=lambda r: (r["s"], r["i"] if r["i"] is not None else 0))
def htok(r):
    for m, o, a, b in (r.get("tb") or []):
        if o == W and m == r["mint"]: return b - a
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
            lot = dict(lot_id=len(LOTS), mint=mint, buy_sig=r["sig"], s=r["s"], i=r["i"], bt=r["bt"], tok=tok, left=float(tok or 0), cost=-r["trade"] / 1e9,
                       sol_curve=(e["sol"] if e else 0) / 1e9, pfee=(e["fee"] if e else 0) / 1e9, cfee=(e["cfee"] if e else 0) / 1e9,
                       buy_txfee=r["txfee"] / 1e9, buy_tip=r["tips"] / 1e9, buy_relay=r["relay"], buy_tip_amt=(r["tip_amt"][0] if r["tip_amt"] else 0),
                       buy_cup=r["cup"], buy_cul=r["cul"], buy_cu=r["cu"], rent_c=r["rent_c"] / 1e9, buy_other=-r["other"] / 1e9, buy_ixn=r["ixn"],
                       vsol_after=(e["vsol"] / 1e9 if e else None), vtok_after=(e["vtok"] if e else None),
                       vsol_before=((e["vsol"] - e["sol"]) / 1e9 if e else None), creator=(e["creator"] if e else None),
                       fbps=(e["fbps"] if e else None), cbps=(e["cbps"] if e else None), nev_buy=r["nev"],
                       proceeds=0.0, sell_txfee=0.0, sell_tip=0.0, sell_other=0.0, rent_x=0.0, sells=[], n_sells=0, close_s=None, close_i=None, close_bt=None,
                       sell_relays=set(), sell_tip_amts=set(), sell_cups=set(), nonpump_sell=False, fail_fee=0.0, n_fail=0, fails=[])
            LOTS.append(lot); q.append(lot)
        else:
            O = 0.0
            if r["events"]:
                e = r["events"][0]; T = float(e["tok"]); Pn = r["trade"] / 1e9; nonpump = False; O = r["other"] / 1e9
            else:
                d = htok(r); T = float(-d) if d else 0.0; nonpump = True
                Pn = (r["sd"] + r["txfee"] + r["tips"] - r["rent_x"]) / 1e9
            C_fee = r["txfee"] / 1e9; C_tip = r["tips"] / 1e9; RX = r["rent_x"] / 1e9
            need = T; taken = []
            # the bot keeps one token account per position (createAccountWithSeed) and sells a whole account at once:
            # match a sell to the open lot holding exactly that many tokens; fall back to FIFO otherwise
            exact = [l for l in q if abs(l["left"] - T) <= 0.5]
            order = exact[:1] + [l for l in q if l not in exact[:1]]
            for l in order:
                if need <= 0.5: break
                take = min(l["left"], need); taken.append((l, take)); l["left"] -= take; need -= take
                if l["left"] <= 0.5: l["left"] = 0.0; q.remove(l); l["close_s"] = r["s"]; l["close_i"] = r["i"]; l["close_bt"] = r["bt"]
            if taken: taken[0][0]["match"] = "exact" if exact else "fifo"
            for l, take in taken:
                f = take / T if T > 0 else 0
                l["proceeds"] += Pn * f; l["sell_txfee"] += C_fee * f; l["sell_tip"] += C_tip * f; l["sell_other"] += O * f
                l["sells"].append((r["sig"], r["s"], r["i"], r["bt"], take, Pn * f, r["relay"], r["cup"])); l["n_sells"] += 1
                l["sell_relays"].add(r["relay"]); l["sell_tip_amts"].add(r["tip_amt"][0] if r["tip_amt"] else 0); l["sell_cups"].add(r["cup"])
                if nonpump: l["nonpump_sell"] = True
            closed = [l for l, t in taken if l["left"] == 0.0]
            if RX and closed:
                for l in closed: l["rent_x"] += RX / len(closed)
            elif RX:
                UNM.append(dict(kind="rent_x_no_lot", sig=r["sig"], mint=mint, bt=r["bt"], sol=RX))
            if need > 0.5:
                UNM.append(dict(kind="sell_unmatched", sig=r["sig"], mint=mint, bt=r["bt"], tok=need, sol=Pn * need / T if T else 0,
                                fee=C_fee * need / T if T else 0, tip=C_tip * need / T if T else 0, rent_x=RX if not taken else 0))
F = []
lots_by_m = collections.defaultdict(list)
for l in LOTS: lots_by_m[l["mint"]].append(l)
for r in rows:
    if not (r["own"] and not r["ok"]): continue
    ix = r["ixn"]; e = json.dumps(r["err"])
    fk = "sell" if "Sell" in ix or "3012" in e or "6003" in e else "buy"
    best = None
    for l in lots_by_m.get(r["mint"], []):
        cb = l["close_bt"] if l["close_bt"] is not None else 10**12
        if l["bt"] - 30 <= r["bt"] <= cb + 30: best = l if best is None or abs(l["bt"] - r["bt"]) < abs(best["bt"] - r["bt"]) else best
    F.append(dict(sig=r["sig"], s=r["s"], i=r["i"], bt=r["bt"], mint=r["mint"], fkind=fk, fee=r["txfee"] / 1e9, err=e, cup=r["cup"], cul=r["cul"],
                  relay=r["relay"], lot_id=best["lot_id"] if best else None, src=r.get("src")))
    if best:
        best["fail_fee"] += r["txfee"] / 1e9; best["n_fail"] += 1; best["fails"].append((r["sig"], r["s"], r["i"], e[-30:]))
W0 = 1793113200; W1 = W0 + 86400
for l in LOTS:
    l["buy_costs"] = l["buy_txfee"] + l["buy_tip"] + l["buy_other"]
    l["is_open"] = l["left"] > 0.5; l["open_tok"] = l["left"]
    l["hold_s"] = (l["close_bt"] - l["bt"]) if l["close_bt"] is not None else None
    l["hold_slots"] = (l["close_s"] - l["s"]) if l["close_s"] is not None else None
    l["first_sell_slots"] = (l["sells"][0][1] - l["s"]) if l["sells"] else None
    l["pnl_cash"] = l["proceeds"] - l["cost"] - l["buy_costs"] - l["sell_txfee"] - l["sell_tip"] + l["sell_other"] - l["rent_c"] + l["rent_x"] - l["fail_fee"]
    l["gross"] = l["proceeds"] - l["cost"]           # curve result after pump/creator fees, before tx fees/tips/rent/failed
    l["day24"] = "D1" if W0 <= l["bt"] < W1 else ("pre" if l["bt"] < W0 else "post")
    l["sell_relays"] = "+".join(sorted(l["sell_relays"])); l["sell_tip_amts"] = tuple(sorted(l["sell_tip_amts"]))
    l["gmgn"] = f"https://gmgn.ai/sol/token/{l['mint']}"; l["buy_tx"] = f"https://solscan.io/tx/{l['buy_sig']}"
pickle.dump(LOTS, open(f"{D}/lots.pkl", "wb"))
pickle.dump(dict(fails=F, unm=UNM), open(f"{D}/fails.pkl", "wb"))
print("lots", len(LOTS), "open", sum(l["is_open"] for l in LOTS), "mints", len(bym), "unmatched", collections.Counter(u["kind"] for u in UNM))
print("fails", len(F), collections.Counter((f["fkind"], f["lot_id"] is not None) for f in F))
c = [l for l in LOTS if not l["is_open"]]
print("closed", len(c), "pnl_cash %.4f gross %.4f" % (sum(l["pnl_cash"] for l in c), sum(l["gross"] for l in c)),
      "win %.1f%%" % (100 * np.mean([l["pnl_cash"] > 0 for l in c])), "hold p50 slots", np.median([l["hold_slots"] for l in c]),
      "size p50 %.4f" % np.median([l["cost"] for l in LOTS]))
