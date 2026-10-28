#!/usr/bin/env python3
"""8yYMhu a6 (read-only): apples-to-apples landing vs E2x1 / haqq / our pre-send fills (e2x1 exec 't7' definition: the previous outside
trade before the buy is a sell >= 0.5 SOL at most 2 slots earlier; chain clock 212 ms/slot), by leader location. Plus: copies of one order
on chain use different nonce accounts? Out: DATA/a6.txt"""
import sys, os, pickle, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, rlib as X
L = pickle.load(open(f"{X.D}/lots.pkl", "rb")); B = pickle.load(open(f"{X.D}/buys.pkl", "rb")); A = pickle.load(open(f"{X.D}/att.pkl", "rb"))
I = pickle.load(open(f"{X.D}/ixs.pkl", "rb"))
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
for lab, sel in (("24h D1", lambda l: X.W0 <= l["bt"] < X.W1), ("all days", lambda l: True)):
    rows = []
    for l in L:
        if not sel(l): continue
        b = B.get(l["lot_id"], {})
        if b.get("prev_buy") is False and b.get("prev_sol", 0) >= 0.5 and b.get("prev_gap", 9) <= 2:
            ms = X.cc(l["s"], l["i"]) - X.cc(b["prev_slot"], b["prev_idx"])
            rows.append((ms, b["prev_gap"], X.area(l["s"])))
    ms = np.array([r[0] for r in rows]); g = np.array([r[1] for r in rows])
    P(f"[t7 def] {lab}: n {len(rows)} ms p25/50/75 {X.pct(ms,25):.0f}/{X.med(ms):.0f}/{X.pct(ms,75):.0f} same slot {100*np.mean(g==0):.0f}%")
    for a in ("DE", "NL", "EU-other", "N.America", "Asia/other"):
        v = [r for r in rows if r[2] == a]
        if len(v) >= 5: P(f"     leader {a:10} n {len(v):5} ms p50 {X.med([r[0] for r in v]):.0f} same slot {100*np.mean([r[1]==0 for r in v]):.0f}%")
P("reference (e2x1 exec x1/x2, same definition): E2x1 44 ms (72% same slot); haqq 45 ms (68%); OUR pre-send fills 20 ms (97%)")
# copies on chain of one order: distinct nonce accounts?
by = collections.defaultdict(list)
for a in A:
    if "trig_slot" in a: by[(a["mint"], a["trig_slot"], a["trig_idx"])].append(a)
pairs = [v for v in by.values() if len(v) >= 2 and sum(1 for a in v if a["sig"] in I) >= 2]
same = sum(1 for v in pairs if len({I[a["sig"]]["nonce"] for a in v if a["sig"] in I}) == 1)
P(f"orders with >=2 on-chain txs both in the RPC sample: {len(pairs)}; same nonce account in both: {same}")
for v in pairs[:5]:
    P("   " + " | ".join(f"{a['out']} {X.ss(a['sig'])} nonce {I[a['sig']]['nonce'][:8]} tip {[t[2] for t in I[a['sig']]['tips']]}" for a in v if a["sig"] in I))
open(f"{X.D}/a6.txt", "w").write("\n".join(out) + "\n")
