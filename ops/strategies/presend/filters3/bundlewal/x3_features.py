#!/usr/bin/env python3
"""BUNDLEWAL step 3 [MEASURED features, no look-ahead]: bundle-ladder features per live position at two cutoffs.
Cutoff A (arm): T2 = trades with slot < trig.slot, or slot == trig.slot and idx <= trig.idx (the engine has seen the trigger);
                rearm = trades with slot < arm_slot.  Cutoff F (fill-1): trades with slot <= fill_slot - 1.
Trades = decoded pump.fun TradeEvents (user = the trader, sol/tok amounts) from the raw recording, create slot from launches.jsonl.
Holdings = net on-curve tokens per user (buys - sells); token transfers between wallets are NOT seen (limitation).
Our own wallets excluded.
Definitions (fixed before scoring):
  buy size of a wallet = SOL of its FIRST buy (bundle wallets usually buy once).
  ladder cluster = wallets (first buy >= MINSOL) sorted by first-buy SOL, greedily grouped while within TOL (relative) of the
                   group's smallest value; a cluster with >= KMIN wallets is a "ladder". Creator counts like anyone else.
  still holding = net tokens >= 50% of tokens bought.
  F1 nl      : number of ladder wallets still holding
  F2 pl      : % supply (1e15) still held by ladder wallets
  F3 cs      : % supply still held by wallets whose first buy was in the create slot (incl. creator dev buy)
  F4 e3      : % supply still held by wallets whose first buy was within create slot .. +3 slots, that belong to a ladder
  F5 lsolr   : sell value (SOL) of ladder holdings at the cutoff curve / real curve SOL (vsol - 30 SOL)
  F6 nearly  : number of distinct wallets with first buy within create..+3 slots still holding (bundle head-count)
Out: /home/moiz/sniper-data/filters3/bundlewal/features.jsonl"""
import json, pickle, glob, os, collections
OUT = "/home/moiz/sniper-data/filters3/bundlewal"
OURS = ("EgxfYgEb", "2g7rYv7y")
MINSOL, TOL, KMIN = 0.02, 0.05, 3
SUP = 1e15
VOFF = 73_000_000_000_000
VSOL0, VTOK0 = 30e9, 1_073_000_000_000_000   # pump.fun initial virtual reserves (K = VSOL0*VTOK0)


def feats(tr, cs):
    first, bought, net = {}, collections.Counter(), collections.Counter()
    vtok = None
    for s, i, buy, sol, tok, user, vt in tr:
        if user.startswith(OURS): pass
        elif buy:
            if user not in first: first[user] = (s, sol / 1e9)
            bought[user] += tok; net[user] += tok
        else:
            net[user] -= tok
        if vt: vtok = vt
    hold = {u: net[u] for u in first if bought[u] > 0 and net[u] >= 0.5 * bought[u]}
    # ladders
    cand = sorted((v[1], u) for u, v in first.items() if v[1] >= MINSOL)
    lad, g = set(), []
    for x, u in cand + [(1e18, None)]:
        if g and x <= g[0][0] * (1 + TOL): g.append((x, u)); continue
        if len(g) >= KMIN: lad.update(uu for _, uu in g)
        g = [(x, u)]
    if vtok is None: vtok = VTOK0
    vsol = VSOL0 * VTOK0 / vtok
    lad_tok = sum(hold[u] for u in lad if u in hold)
    # sell value of lad_tok on curve
    sellv = vsol - VSOL0 * VTOK0 / (vtok + lad_tok) if lad_tok else 0.0
    real_sol = max(vsol - VSOL0, 1e8)
    early = {u for u, v in first.items() if cs is not None and v[0] <= cs + 3}
    return dict(nl=sum(1 for u in lad if u in hold), pl=100 * lad_tok / SUP,
                cs=100 * sum(hold[u] for u in hold if cs is not None and first[u][0] == cs) / SUP,
                e3=100 * sum(hold[u] for u in lad if u in hold and u in early) / SUP,
                lsolr=sellv / real_sol, nearly=sum(1 for u in early if u in hold),
                ntr=len(tr), nbuyers=len(first), vsol=vsol / 1e9)


if __name__ == "__main__":
    T, CR = {}, {}
    for f in sorted(glob.glob(f"{OUT}/trades_*.pkl")):
        d = pickle.load(open(f, "rb"))
        for m, v in d["trades"].items():
            if m not in T or len(v) > len(T[m]): T[m] = v
        CR.update(d["create"])
    o = open(f"{OUT}/features.jsonl", "w"); cov = collections.Counter()
    for l in open(f"{OUT}/positions.jsonl"):
        p = json.loads(l)
        m = p["mint"]; tr = T.get(m); c = CR.get(m)
        ok = bool(tr) and c is not None and tr[0][0] >= c[0] and tr[0][0] - c[0] <= 2
        cov[(p["split"], ok)] += 1
        if ok:
            cs = c[0]
            a_s, a_i = p["arm_slot"], p.get("arm_idx")
            if p["kind"] == "t2" and a_i is not None:
                ta = [t for t in tr if t[0] < a_s or (t[0] == a_s and t[1] <= a_i)]
            else:
                ta = [t for t in tr if t[0] < a_s]
            tf = [t for t in tr if t[0] <= p["fill_slot"] - 1]
            p["A"] = feats(ta, cs); p["F"] = feats(tf, cs); p["age"] = a_s - cs
        p["cov"] = ok
        o.write(json.dumps(p) + "\n")
    print(dict(cov))
