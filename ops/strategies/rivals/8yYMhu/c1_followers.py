#!/usr/bin/env python3
"""8yYMhu c1 (read-only): who buys right after him? Per landed buy: outside BUYS on the mint after his buy up to +3 slots.
Wallets that do it on many of his lots = copy-traders/followers (their buys lift his exit price; a copy of his strategy without them
would not get that lift). Compares with lookalike sells he did not take (same imitation-score band) to measure the follower lift.
Out: DATA/c1.txt"""
import sys, os, pickle, collections, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, rlib as X, tlib as T
L = pickle.load(open(f"{X.D}/lots.pkl", "rb")); wid = T.uid()[X.W]; users = T.names()[1]
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
cnt = collections.Counter(); sol_ = collections.Counter(); first = collections.Counter(); nl = 0
per_lot = []
for l in L:
    tr = T.trades(l["mint"])
    if tr is None: continue
    key = tr["slot"].astype(np.int64) * 4096 + tr["idx"].astype(np.int64)
    kb = l["s"] * 4096 + l["i"]; p = int(np.searchsorted(key, kb))
    if not (p < len(tr) and key[p] == kb): continue
    nl += 1
    w = tr[p + 1:]; w = w[(w["slot"] <= l["s"] + 3) & (w["user"] != wid) & (w["buy"] == 1)]
    seen = set()
    for q, t in enumerate(w):
        u = int(t["user"])
        if u in seen: continue
        seen.add(u); cnt[u] += 1; sol_[u] += int(t["sol"]) / 1e9
        if q == 0: first[u] += 1
    per_lot.append((l["lot_id"], len(seen), float(w["sol"].sum()) / 1e9))
P(f"his landed buys on tape {nl}; outside buyers within 3 slots after him: mean {np.mean([x[1] for x in per_lot]):.2f} wallets, {np.mean([x[2] for x in per_lot]):.2f} SOL per lot")
P("top wallets buying within 3 slots after his buys (lots, share of his lots, SOL, times first after him):")
for u, c in cnt.most_common(25):
    P(f"   {users[u]}  {c:5}  {100*c/nl:5.1f}%  {sol_[u]:8.1f} SOL  first {first[u]}")
pickle.dump(dict(cnt=cnt, sol=sol_, first=first, per_lot=per_lot, nl=nl), open(f"{X.D}/c1.pkl", "wb"))
open(f"{X.D}/c1.txt", "w").write("\n".join(out) + "\n")
