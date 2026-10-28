#!/usr/bin/env python3
"""8yYMhu w1 (read-only, INFERRED replay): what if our pre-send armed on smaller holders ("any >=1 SOL seller") instead of whales >=6 %?
Arm event = a wallet's position on a token first crosses X % of supply (X = 6 / 4 / 3 / 2 / 1) via a buy (creator create-slot buys excluded,
as live). Window = 10 slots after the arming buy (live config). Fill = that wallet sells >= 1 SOL with a >= 12 % price drop inside the
window (our 0.88x limit). Cost = 0.153 mSOL of failed-try fees per arm (MEASURED FRA r28: 11,315 landed tries x 5,120 lamports / 375 arms,
k=8) ; value = paper 0.75 SOL trade from the universe at entry e0 / e73 with exit +1 / +2 slots (our ~200 ms exit), after pump fees.
Window 10-25 13:00 -> 10-29 00:50 PKT. Out: DATA/w1.txt"""
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, rlib as X, tlib as T
M, um, ua, ub = T.tape()
U = dict(np.load(f"{X.D}/uni2.npz"))
ukey = {(int(m), int(s), int(i)): q for q, (m, s, i) in enumerate(zip(U["mint"], U["slot"], U["idx"]))}
TA, TB = 1792915200, 1793220600; days = (TB - TA) / 86400
THR = (6, 4, 3, 2, 1); ARM_COST = 0.000153
CR = json.load(open("/home/moiz/sniper-data/dv8/tab/creates.json")); CR.update(json.load(open("/home/moiz/sniper-data/e2x1_dissect/select/creates_new.json")))
mid = T.mid(); cslot = {mid[m]: int(v["slot"]) for m, v in CR.items() if m in mid and v.get("slot")}
arms = collections.Counter(); fills = collections.defaultdict(list); DL = (0.05, 0.08, 0.12)
for p in range(len(um)):
    a0, b0 = int(ua[p]), int(ub[p])
    if b0 - a0 < 3: continue
    tr = np.asarray(M[a0:b0]); k = int(um[p]); cs = cslot.get(k, int(tr["slot"][0]))
    o = np.lexsort((tr["idx"], tr["slot"], tr["user"])); t2 = tr[o]
    sgn = np.where(t2["buy"] == 1, 1.0, -1.0) * t2["tok"].astype(np.float64)
    newu = np.ones(len(t2), bool); newu[1:] = t2["user"][1:] != t2["user"][:-1]
    grp = np.cumsum(newu) - 1; cum = np.cumsum(sgn); base = cum[newu][grp] - sgn[newu][grp]; pos = cum - base   # position after each trade
    pct = 100 * pos / 1e15
    for X_ in THR:
        cross = (t2["buy"] == 1) & (pct >= X_) & ((pct - 100 * sgn / 1e15) < X_) & (t2["slot"] != cs) & (t2["bt"] >= TA) & (t2["bt"] < TB)
        for q in np.nonzero(cross)[0]:
            arms[X_] += 1
            u = t2["user"][q]; s0 = int(t2["slot"][q])
            # same user's sells >= 1 SOL within 10 slots after
            m = (t2["user"] == u) & (t2["buy"] == 0) & (t2["sol"] >= 1_000_000_000) & (t2["slot"] > s0) & (t2["slot"] <= s0 + 10)
            m &= np.arange(len(t2)) > q
            cand = [ukey.get((k, int(t2["slot"][qq]), int(t2["idx"][qq]))) for qq in np.nonzero(m)[0]]
            cand = [c for c in cand if c is not None]
            for dl in DL:
                for ui in cand:
                    if U["drop"][ui] >= dl: fills[(X_, dl)].append(ui); break
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
P(f"window {days:.2f} days; arm cost {ARM_COST*1000:.3f} mSOL/arm (failed tries); fill = arming wallet dumps >=1 SOL with >=12% drop within 10 slots")
P("| arm threshold (% supply) | fill on a drop of | arms/day | fills/day | fills per arm | his take rate on those dumps | paper mSOL/fill e0+1 / e0+2 / e73+1 / e73+2 | net SOL/day at e0+2 (after arm cost) |")
P("|---|---|---|---|---|---|---|---|")
tk = U["taken"] > 0
for X_ in THR:
  for dl in DL:
    f = np.array(fills[(X_, dl)], int); n = len(f)
    if not n: continue
    vals = [1000 * np.nanmean(U[c][f]) for c in ("r_e0_1", "r_e0_2", "r_e73_1", "r_e73_2")]
    net = (np.nansum(U["r_e0_2"][f]) - ARM_COST * arms[X_]) / days
    P(f"| >= {X_}% | >= {100*dl:.0f}% | {arms[X_]/days:,.0f} | {n/days:,.0f} | {n/arms[X_]:.3f} | {100*tk[f].mean():.0f}% | " + " / ".join(f"{v:+.1f}" for v in vals) + f" | {net:+.2f} |")
open(f"{X.D}/w1.txt", "w").write("\n".join(out) + "\n")
