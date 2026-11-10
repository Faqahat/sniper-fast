#!/usr/bin/env python3
"""TIMING step 1 [MEASURED, read-only]: per LIVE fill (GUARDS fills.pkl, 20 live runs) the holder context on the decoded per-mint tape
(GUARDS tapes_fills.pkl, chain order; our wallets removed from balances):
  - every wallet holding >= 2% of supply strictly before OUR BUY's landing position (balance, first-buy slot/key, cost basis, creator flag,
    same-first-slot cluster with other holders), and at the try's SIGNING position and at the TRIGGER position
  - every outside sell between our buy landing and our (last) sell landing = the in-hold sellers (wallet, SOL, tokens)
  - label per holder: sold inside our hold (and how much)
Big loss = P&L scaled to 0.696 SOL <= -0.05 (WHO/GUARDS definition: pnl x 0.696 / fill spend).
Out: /home/it/sniper-data/prevent/timing/fillctx.pkl  + wallets.json (the wallet set W to profile)"""
import pickle, json, collections, bisect
import numpy as np
D = "/home/it/sniper-data"
OUT = f"{D}/prevent/timing"
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
SUP = 1e15
F = pickle.load(open(f"{D}/prevent/guards/fills.pkl", "rb"))
TP = pickle.load(open(f"{D}/prevent/guards/tapes_fills.pkl", "rb"))
CR = pickle.load(open(f"{D}/prevent/who/creates.pkl", "rb"))


def K(s, i, j=0): return (int(s) << 24) | (int(i) << 6) | int(j)


out = []; W = collections.Counter(); miss = 0
for f in F:
    rows = TP.get(f["mint"])
    if not rows: miss += 1; continue
    keys = [K(r[0], r[1], r[2]) for r in rows]
    kb = K(f["slot"], f["idx"], 0)
    # our buy row (any j) -> exact key
    for n, r in enumerate(rows):
        if r[0] == f["slot"] and r[1] == f["idx"] and r[8] in OURS: kb = keys[n]; break
    cl = f["close"] or {}
    sl = cl.get("sell_land")
    sells = f.get("sells") or []
    if sells: sl2 = max(sells, key=lambda x: (x[0], x[1])); ks = K(sl2[0], sl2[1], 0)
    elif sl: ks = K(sl[0], sl[1], 0)
    else: ks = K(f["slot"] + 2, 0, 0)
    sell_slot = ks >> 24
    cre = CR.get(f["mint"]); creator = cre[0] if cre else None; cslot = cre[1] if cre else None
    # balances, first buy, cost per wallet up to a key
    def state(kcut):
        bal = collections.defaultdict(int); first = {}; fkey = {}; cost = collections.defaultdict(int); nb = collections.Counter(); ns = collections.Counter()
        for n, r in enumerate(rows):
            if keys[n] >= kcut: break
            u = r[8]
            if u in OURS: continue
            if r[3]:
                bal[u] += r[5]; cost[u] += r[4]; nb[u] += 1
                if u not in first: first[u] = r[0]; fkey[u] = keys[n]
            else:
                bal[u] -= r[5]; cost[u] -= r[4]; ns[u] += 1
        return bal, first, fkey, cost, nb, ns
    bal, first, fkey, cost, nb, ns = state(kb)
    # price just before our buy (post-trade reserves of the last outside trade before kb)
    kprev = bisect.bisect_left(keys, kb) - 1
    while kprev >= 0 and rows[kprev][8] in OURS: kprev -= 1
    p_now = rows[kprev][6] / rows[kprev][7] if kprev >= 0 else None
    H = {}
    for u, b in bal.items():
        if b >= 0.02 * SUP:
            H[u] = dict(bal=b, pct=100 * b / SUP, first=first.get(u), fkey=fkey.get(u), cost=cost[u], nb=nb[u], ns=ns[u],
                        creator=(u == creator), whale=(u == f["whale"]))
    # same-first-slot clusters among >=1% holders
    fs1 = collections.defaultdict(list)
    for u, b in bal.items():
        if b >= 0.01 * SUP and u in first: fs1[first[u]].append(u)
    for u in H: H[u]["clu"] = len(fs1.get(H[u]["first"], [])) - 1
    # in-hold sells
    ih = collections.defaultdict(lambda: [0, 0, 0])
    for n, r in enumerate(rows):
        if keys[n] <= kb: continue
        if keys[n] >= ks: break
        if r[8] in OURS or r[3]: continue
        x = ih[r[8]]; x[0] += r[4]; x[1] += r[5]; x[2] += 1
    # sells in the next 3 slots after our buy (fixed horizon, independent of our sell timing)
    nx = collections.defaultdict(lambda: [0, 0, None])
    for n, r in enumerate(rows):
        if keys[n] <= kb: continue
        if r[0] > f["slot"] + 3: break
        if r[8] in OURS or r[3]: continue
        x = nx[r[8]]; x[0] += r[4]; x[1] += r[5]
        if x[2] is None: x[2] = keys[n]
    # holders at signing and trigger
    def holders_at(kcut, thr=0.02):
        b2, f2, _, c2, _, _ = state(kcut)
        return {u: (b, f2.get(u), c2[u]) for u, b in b2.items() if b >= thr * SUP}
    sp = f.get("sign_pos")
    Hs = holders_at(K(sp[0], sp[1], (sp[2] or 0) + 1)) if sp else None
    Ht = holders_at(K(f["trig_slot"], f["trig_idx"], (f["trig_j"] or 0) + 1)) if f.get("trig_slot") else None
    spend = f["spend"] or 696_000_000
    pnl = f["pnl"]; p696 = pnl * 0.696e9 / spend if pnl is not None else None
    rec = dict(run=f["run"], ses=f["ses"], kind=f["kind"], w=f["w"], mint=f["mint"], whale=f["whale"], creator=creator, cslot=cslot,
               slot=f["slot"], idx=f["idx"], t=f["t"], kb=kb, ks=ks, sell_slot=sell_slot, trig_slot=f.get("trig_slot"), trig_t=f.get("trig_t"),
               sign_slot=f.get("sign_slot"), sign_t=f.get("sign_t"), en_slot=f.get("en_slot"), age=f.get("age"), spend=spend, pnl=pnl, p696=p696,
               exit=(cl.get("exit_why")), held_s=cl.get("held_s"), p_now=p_now, H=H, Hs=Hs, Ht=Ht,
               inhold={u: tuple(v) for u, v in ih.items()}, next3={u: tuple(v) for u, v in nx.items()})
    out.append(rec)
    for u in H: W[u] += 1
    for u in (Hs or {}): W[u] += 1
    for u in (Ht or {}): W[u] += 1
    for u, v in ih.items():
        if v[0] >= 50_000_000: W[u] += 1
    if creator: W[creator] += 1
    if f["whale"]: W[f["whale"]] += 1
pickle.dump(out, open(f"{OUT}/fillctx.pkl", "wb"))
json.dump(sorted(W), open(f"{OUT}/wallets.json", "w"))
big = [r for r in out if r["p696"] is not None and r["p696"] <= -0.05]
print("fills", len(out), "missing tape", miss, "wallets", len(W), "big losses", len(big), "sum", round(sum(r["p696"] for r in big), 2))
print("holders>=2% per fill", np.mean([len(r["H"]) for r in out]).round(2), "fills w/ in-hold sells", sum(1 for r in out if r["inhold"]))
