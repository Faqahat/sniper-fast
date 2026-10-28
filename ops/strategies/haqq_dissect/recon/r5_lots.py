#!/usr/bin/env python3
"""recon step 5 (read-only): exact code-matched lots from the per-tx table (r4 table_all.pkl).
Lot = one buy event. Cost = SOL the curve + pump fee + creator fee took (TradeEvent, exact lamports); buy tx cost = fee + tips of that tx.
A sell takes tokens from open lots of ITS OWN CODE on the mint first (FIFO), then from any open lot (FIFO); its net proceeds
(sol - fee - creator fee; PumpSwap sells: the WSOL account's gain) and its fee + tips are split by tokens taken.
Open at the end of the recordings -> marked at the exact curve sell quote of the remaining tokens at the tape's last state
(dv8/tab, ends 10-28 01:12 PKT) net of the pump fee bps of that last trade. A second mark at W1 (last trade before W1) for the bridge.
Out: recon/lots.pkl"""
import json, pickle, collections, sys, os
import numpy as np
H = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
W0, W1 = 1793038500, 1793124900
OUT = "/home/moiz/sniper-data/haqq_dissect/recon"
TAB = "/home/moiz/sniper-data/dv8/tab"
rows = pickle.load(open(f"{OUT}/table_all.pkl", "rb"))
trades = [r for r in rows if r["cls"] in ("buy", "sell", "swap_sell") and r["ev"]]
bym = collections.defaultdict(list)
for r in trades:
    for j, e in enumerate(r["ev"]): bym[e["mint"]].append((r, j, e))
LOTS = []; UNM = []
for mint, lst in bym.items():
    lst.sort(key=lambda t: (t[0]["s"], t[0]["i"], t[1]))
    q = []
    for r, j, e in lst:
        ne = len(r["ev"])
        if e["buy"]:
            lot = dict(mint=mint, code=r["code"], sig=r["sig"], s=r["s"], i=r["i"], bt=r["bt"], inw=W0 <= r["bt"] < W1, tok=e["tok"], left=float(e["tok"]),
                       cost=(e["sol"] + e["fee"] + e["cfee"]) / 1e9, btxc=(r["txfee"] + r["tips"]) / 1e9 / ne, rent=r["rent"] / 1e9 / ne,
                       out_w=0.0, out_after=0.0, stxc_w=0.0, stxc_after=0.0, sells=[], close_bt=None, same_code_tok=0.0, other_code_tok=0.0,
                       swap=False)
            LOTS.append(lot); q.append(lot)
        else:
            T = float(e["tok"]); P = (e["sol"] - e["fee"] - e["cfee"]) / 1e9; C = (r["txfee"] + r["tips"]) / 1e9 / ne
            need = T; inw = W0 <= r["bt"] < W1; after = r["bt"] >= W1
            for pas in (0, 1):
                for l in list(q):
                    if need <= 0.5: break
                    if l["left"] <= 0.5: continue
                    if pas == 0 and l["code"] != r["code"]: continue
                    take = min(l["left"], need); f = take / T if T > 0 else 0
                    if after: l["out_after"] += P * f; l["stxc_after"] += C * f
                    elif inw: l["out_w"] += P * f; l["stxc_w"] += C * f
                    else: l["out_pre"] = l.get("out_pre", 0) + P * f; l["stxc_pre"] = l.get("stxc_pre", 0) + C * f
                    if pas == 0: l["same_code_tok"] += take
                    else: l["other_code_tok"] += take
                    l["left"] -= take; need -= take; l["sells"].append((r["sig"], r["bt"], take, r["code"]))
                    if e.get("swap"): l["swap"] = True
                    if l["left"] <= 0.5: l["left"] = 0.0; l["close_bt"] = r["bt"]; q.remove(l)
            if need > 0.5:
                UNM.append(dict(mint=mint, code=r["code"], sig=r["sig"], bt=r["bt"], inw=inw, tok=need, P=P * need / T, C=C * need / T))
    for l in q:
        if l["left"] < 0.005 * l["tok"]: l["dust"] = True
# ---- marks from the tape
open_mints = sorted({l["mint"] for l in LOTS if l["left"] > 0} | {l["mint"] for l in LOTS if l["inw"] and (l["close_bt"] is None or l["close_bt"] >= W1)})
ids = json.load(open(f"{TAB}/ids.json")); idm = {k: i for i, k in enumerate(ids)}
T = np.load(f"{TAB}/trades.npy", mmap_mode="r")
want = np.array(sorted(idm[m] for m in open_mints if m in idm), dtype=np.uint32)
mm = np.asarray(T["mint"])
sel = np.flatnonzero(np.isin(mm, want)); del mm
sub = np.asarray(T[sel])
last_end = {}; last_w1 = {}
o = np.lexsort((sub["j"], sub["idx"], sub["slot"]))
for k in o.tolist():
    t = sub[k]; m = ids[int(t["mint"])]
    st = (int(t["vsol"]), int(t["vtok"]), int(t["fee_bps"]) + int(t["cfee_bps"]), int(t["bt"]), int(t["slot"]))
    last_end[m] = st
    if t["bt"] < W1: last_w1[m] = st
tape_end_bt = int(sub["bt"].max()) if len(sub) else None
def quote(st, tok):
    if st is None or tok <= 0: return 0.0
    vs, vt, bps, _, _ = st
    out = vs - vs * vt / (vt + tok)
    return out * (1 - bps / 1e4) / 1e9
for l in LOTS:
    l["mark_end"] = quote(last_end.get(l["mint"]), l["left"]) if l["left"] > 0 else 0.0
    l["mark_src"] = "tape" if l["mint"] in last_end else ("none" if l["left"] > 0 else "")
    # tokens still held at W1 (for lots opened in window): left + tokens sold after W1
    if l["inw"]:
        tok_w1 = l["left"] + sum(t for sg, bt, t, c in l["sells"] if bt >= W1)
        l["tok_w1"] = tok_w1; l["mark_w1"] = quote(last_w1.get(l["mint"]), tok_w1) if tok_w1 > 0 else 0.0
    l["pnl"] = l["out_w"] + l["out_after"] + l.get("out_pre", 0) + l["mark_end"] - l["cost"] - l["btxc"] - l["stxc_w"] - l["stxc_after"] - l.get("stxc_pre", 0)
pickle.dump(dict(lots=LOTS, unm=UNM, tape_end_bt=tape_end_bt), open(f"{OUT}/lots.pkl", "wb"))
inw = [l for l in LOTS if l["inw"]]
print(f"lots {len(LOTS):,}; opened in window {len(inw):,}; open at end of recordings (window lots) {sum(1 for l in inw if l['left'] > 0)}; unmatched sell pieces {len(UNM)} (in window {sum(1 for u in UNM if u['inw'])}, SOL {sum(u['P'] for u in UNM if u['inw']):.4f})")
print("same-code share of sold tokens (window lots):", sum(l["same_code_tok"] for l in inw) / max(1, sum(l["same_code_tok"] + l["other_code_tok"] for l in inw)))
print("tape end", tape_end_bt)
