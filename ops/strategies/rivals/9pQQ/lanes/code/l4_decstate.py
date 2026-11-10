#!/usr/bin/env python3
"""LANES step 4: from the RPC-fetched instruction data, find the curve state each 9pQQ buy/sell was PRICED on.
BUY:  min_tokens_out = E_buy(state) / 1.15   (constant found on the sample: exact ratio 0.869565 when nothing moved)
SELL: min_sol_out    = K_s * E_sell(state)   (K_s fitted here)
For each sampled tx: candidate states = post-state of every landed curve trade on the mint in the 400 slots before it (+ its own pre-state).
Output per tx: implied ratio vs landing pre-state, best-matching state (offset back in trades, same slot?, slot gap, who made it).
usage: l4_decstate.py RPCFILE OUTJSONL"""
import sys, json, numpy as np, collections
sys.path.insert(0, "/home/it/sniper/ops/strategies/rivals/9pQQ/lanes/code")
import rpcdec
D = "/home/it/sniper-data/rivals/9pQQ/lanes"; W = "9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN"
V = 73_000_000_000_000; TOTAL = 10**15; K = 30_000_000_000 * 1_073_000_000_000_000
XB = {700000000: 691358023, 480000000: 474074074}
def vres(c):
    vt = float(c) + V; return K / vt, vt
def ebuy(c, x):
    vs, vt = vres(c); return vt * x / (vs + x)
def esell(c, t):
    vs, vt = vres(c); return vs * t / (vt + t)
rpc = collections.defaultdict(list)
for l in open(sys.argv[1]):
    d = json.loads(l); rpc[d["run"]].append(d)
fo = open(sys.argv[2], "w")
for run, L in rpc.items():
    import llib
    t = llib.load(run); users = t.users; mints = t.mints; mix = t.mix; wid = t.wid; ms = t.ms
    a = np.stack([t.s, t.i, t.bt, t.u, t.m, t.tok, t.sol, t.cpre, t.cpost], 1); del t
    for d in L:
        o = rpcdec.dec(d["tx"])
        if "pargs" not in o: continue
        raw_m = None
        keys = d["tx"]["transaction"]["message"]["accountKeys"]
        cand = [k for k in keys if k in mix and not k.startswith("So1111")]
        if not cand: continue
        m = mix[cand[0]]; seg = a[ms[m]:ms[m + 1]]
        s, i = d["s"], d["i"]
        before = seg[(seg[:, 0] < s) | ((seg[:, 0] == s) & (seg[:, 1] < i))]
        before = before[before[:, 0] >= s - 400]
        mine = seg[(seg[:, 0] == s) & (seg[:, 1] == i)]
        isbuy = o["pdisc"] == "e1f7501ed5b38488" or o["pargs"][0] in XB
        cp = lambda c: TOTAL if c < 100e12 else c
        states = [(cp(r[8]), int(r[0]), int(r[1]), int(r[3]), int(r[5]), int(r[6])) for r in before]
        if len(mine): land = cp(mine[0][7])
        elif states: land = states[-1][0]
        else: continue
        if isbuy:
            x = XB.get(o["pargs"][0], o["pargs"][0] * 10000 // 10125); mo = o["pargs"][1]
            f = lambda c: mo * 1.15 / ebuy(c, x)
        else:
            t = o["pargs"][0]; mo = o["pargs"][1]
            f = lambda c: mo / esell(c, t)
        r_land = f(land)
        best = None
        for k in range(len(states) - 1, -1, -1):
            q = f(states[k][0])
            if best is None or abs(q - (1.0 if isbuy else 0.5)) < abs(best[0] - (1.0 if isbuy else 0.5)):
                best = (q, len(states) - 1 - k, states[k])
        rec = dict(run=run, sig=d["sig"], kind=d["kind"], buy=isbuy, s=s, i=i, mint=cand[0], landed=bool(len(mine)), r_land=r_land,
                   n_before=len(states), bh=o["bh"], jito=[t_[0] for t_ in o.get("tips", []) if not t_[0].startswith("astra")],
                   amt=o["pargs"][0], minout=mo, err=o["err"])
        if best:
            q, back, st = best
            rec.update(best_q=q, best_back=back, best_ds=s - st[1], best_di=(i - st[2]) if st[1] == s else None,
                       best_user=users[st[3]], best_tok=st[4], best_sol=st[5], best_is_own=bool(st[3] == wid))
        # all exact-ish matches
        if isbuy:
            rec["matches"] = [(len(states) - 1 - k, s - states[k][1], int(states[k][3] == wid)) for k in range(len(states)) if abs(f(states[k][0]) - 1) < 3e-5][-5:]
        fo.write(json.dumps(rec) + "\n")
    print(run, len(L), flush=True)
