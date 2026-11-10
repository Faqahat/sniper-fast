#!/usr/bin/env python3
"""Our real round trips (tape, EgxfYgEb) split by 9pQQ's state on that token at our buy: holding it now, round-tripped it before
(in the recording), never touched it.  And whether 9pQQ then bought inside our hold.  Real P&L (fees included).  Read-only.
usage: i2_ours_k.py"""
import numpy as np, collections, json
import tlib9 as L
out = {}
for r in L.RUNS:
    t = L.load_tape(r); wid = t.user_ix[L.W]; oid = t.user_ix.get(L.OURS, -1)
    g = collections.defaultdict(list); come = collections.defaultdict(list)
    rows = np.where(t.u == oid)[0]; bym = collections.defaultdict(list)
    for j in rows: bym[int(t.m[j])].append(int(j))
    for m, js in bym.items():
        js.sort(); a0 = t.mstart[m]; k = 0
        while k < len(js):
            jb = js[k]
            if t.tok[jb] <= 0: k += 1; continue
            bal = t.tok[jb]; net = t.sol[jb]; q = k + 1
            while q < len(js) and bal > 1000: bal += t.tok[js[q]]; net += t.sol[js[q]]; q += 1
            if bal > 1000: break
            je = js[q - 1]
            pre = slice(a0, jb); h9 = t.tok[pre][t.u[pre] == wid].sum()
            n9 = int((t.u[pre] == wid).sum())
            st = "9pQQ holding" if h9 > 1000 else ("9pQQ traded before" if n9 else "9pQQ never")
            g[st].append(net / 1e9)
            act = "ntr<200" if jb - a0 < 200 else "ntr>=200"
            g[st + " | " + act].append(net / 1e9); come[st + " | " + act].append(False)
            came = bool(((t.u[jb + 1:je] == wid) & (t.tok[jb + 1:je] > 0)).any())
            come[st].append(came)
            k = q
    out[L.DAY[r]] = {k: dict(n=len(v), net=round(sum(v), 3), msol=round(1000 * np.mean(v), 2), p9_came=round(float(np.mean(come[k])), 3)) for k, v in g.items()}
    print(L.DAY[r], json.dumps(out[L.DAY[r]]))
json.dump(out, open("/home/it/sniper/ops/strategies/rivals/9pQQ/ours_k.json", "w"), indent=1)
