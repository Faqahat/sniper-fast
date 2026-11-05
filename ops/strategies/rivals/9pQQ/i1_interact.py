#!/usr/bin/env python3
"""9pQQ interactions.  (1) OUR round trips (tape, EgxfYgEb) split by what 9pQQ did around them: bought after us inside our hold,
bought before us (<=10 slots), sold inside our hold, absent.  (2) For 9pQQ's DIP entries: which known bots bought the same dump
(within 3 slots) before / after it.  (3) Who it sells into / after: the wallets trading right before and right after its sells, and
who buys after its buys (followers).  Read-only.  usage: i1_interact.py"""
import pickle, collections, json
import numpy as np
import tlib9 as L

BOTS = {"OURS": L.OURS, "haqqiUUX": "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq", "haqq6qnV": "haqq6qnVBCZt97amh9VUFZRFCkD6NJxoYifacCuqqqq",
        "8yYMhu": "8yYMhuYo1LzgCmeeg3vRkhRtJ8xFC7v7S4ufABtQXjS3", "E2x1": "E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb",
        "HkQ7": "HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ", "DYXD": "DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw",
        "Grozoe": "Grozoe2Lk9yu7kWPcCMuWEbrnuBYseBExkYAuHPRJUdJ"}
res = {}
for r in L.RUNS:
    t = L.load_tape(r); wid = t.user_ix[L.W]; oid = t.user_ix.get(L.OURS, -1)
    bid = {k: t.user_ix.get(v, -9) for k, v in BOTS.items()}
    name = {v: k for k, v in bid.items()}
    day = L.DAY[r]; R = res.setdefault(day, {})
    # (1) our trips
    g = collections.defaultdict(list)
    if oid >= 0:
        rows = np.where(t.u == oid)[0]
        bym = collections.defaultdict(list)
        for j in rows: bym[int(t.m[j])].append(int(j))
        for m, js in bym.items():
            js.sort(); a0 = t.mstart[m]; a1 = t.mstart[m + 1]
            k = 0
            while k < len(js):
                jb = js[k]
                if t.tok[jb] <= 0: k += 1; continue
                bal = t.tok[jb]; net = t.sol[jb]; q = k + 1
                while q < len(js) and bal > 1000:
                    bal += t.tok[js[q]]; net += t.sol[js[q]]; q += 1
                if bal > 1000: break
                je = js[q - 1]
                seg = slice(jb + 1, je)
                n9b_after = int(((t.u[seg] == wid) & (t.tok[seg] > 0)).sum())
                n9s_in = int(((t.u[seg] == wid) & (t.tok[seg] < 0)).sum())
                lo = int(np.searchsorted(t.s[a0:a1], t.s[jb] - 10)) + a0
                n9b_before = int(((t.u[lo:jb] == wid) & (t.tok[lo:jb] > 0)).sum())
                key = "9pQQ bought after us (in our hold)" if n9b_after else ("9pQQ bought <=10 slots before us" if n9b_before else "9pQQ absent")
                g[key].append(net / 1e9)
                if n9s_in: g["9pQQ sold inside our hold"].append(net / 1e9)
                k = q
    R["ours"] = {k: dict(n=len(v), net=round(sum(v), 3), msol=round(1000 * np.mean(v), 2)) for k, v in g.items()}
    # (2) DIP entries: bots on the same dump
    T = [x for x in pickle.load(open(f"{L.OUT}/trips_{r}.pkl", "rb")) if x.get("tape_ok") and (x.get("dump_sol") or 0) >= 0.5]
    before = collections.Counter(); after = collections.Counter(); tot = 0
    for x in T:
        mi = t.mint_ix[x["mint"]]; a0 = t.mstart[mi]; a1 = t.mstart[mi + 1]
        S = t.s[a0:a1]; I = t.i[a0:a1]; U = t.u[a0:a1]; TK = t.tok[a0:a1]
        jb = int(np.searchsorted(S * 10000 + I, x["bs"] * 10000 + x["bi"]))
        lo = int(np.searchsorted(S, x["bs"] - 3)); hi = int(np.searchsorted(S, x["bs"] + 3, side="right"))
        tot += 1
        for j in range(lo, hi):
            if TK[j] > 0 and U[j] in name and U[j] != wid:
                (before if j < jb else after)[name[U[j]]] += 1
    R["dip_same_dump"] = {"n_dip_trips": tot, "bot_before_9pQQ": dict(before), "bot_after_9pQQ": dict(after)}
    # (3) followers and sell counterparties
    T = [x for x in pickle.load(open(f"{L.OUT}/trips_{r}.pkl", "rb")) if x.get("tape_ok") and x["net"] is not None]
    fol = collections.Counter(); folsol = 0.0; nfol = []
    for x in T:
        mi = t.mint_ix[x["mint"]]; a0 = t.mstart[mi]; a1 = t.mstart[mi + 1]
        S = t.s[a0:a1]; I = t.i[a0:a1]; U = t.u[a0:a1]; TK = t.tok[a0:a1]; SL = t.sol[a0:a1]
        jb = int(np.searchsorted(S * 10000 + I, x["bs"] * 10000 + x["bi"]))
        hi = int(np.searchsorted(S, x["bs"] + 3, side="right"))
        us = set(); v = 0.0
        for j in range(jb + 1, hi):
            if TK[j] > 0 and U[j] != wid: us.add(int(U[j])); v += -SL[j] / 1e9
        nfol.append(len(us)); folsol += v
        for u in us: fol[t.users[u]] += 1
    R["followers_3slots"] = dict(per_trip_wallets=round(float(np.mean(nfol)), 2), per_trip_sol=round(folsol / len(T), 3),
                                 top=[(u[:10], c, round(c / len(T), 3)) for u, c in fol.most_common(12)])
    sc = collections.Counter(x.get("nx_user", "")[:10] for x in T if x.get("nx_side") == 1 and x.get("nx_gap", 99) <= 1)
    pc = collections.Counter(x.get("xlast_user", "")[:10] for x in T if x.get("xlast_side") == -1 and x.get("xlast_gap", 99) <= 1)
    R["after_its_sell_next_buyer"] = sc.most_common(8)
    R["sell_preceded_by_seller"] = pc.most_common(8)
    R["exit_next_trade_side"] = dict(collections.Counter(x.get("nx_side") for x in T))
    print(day, json.dumps(R, default=str), flush=True)
json.dump(res, open("/home/moiz/sniper/ops/strategies/rivals/9pQQ/interact.json", "w"), indent=1, default=str)
