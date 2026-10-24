#!/usr/bin/env python3
# COPY-TRADE replay (read-only, offline): we see a leader wallet's buy tx in our feed (its arrival ms after the create),
# then send ours; ours lands DELTA ms later. Everything our engine saw before that is ahead of us (incl. the leader).
# Leaders: the case-study wallets. Exits: all rules from run_fwd2. One row per (launch, leader).
import sys, os, json, gzip, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from run_fwd2 import RULES, NAMES, L, O, A
from multiprocessing import Pool
OUT = sys.argv[1] if len(sys.argv) > 1 else "copy.jsonl.gz"
LEAD = {"9Sh2fd": "9Sh2fdqMQcec7W9LzzfvkYphrdyR3S8aUBsKdv9xNYa1", "DGmspi": "DGmspiBs2ePJ7WgN1pyX5RJDpzhyxYrBN1P4bXNC1NR3", "D24ipY": "D24ipYXuDt6PXEPV6rZqfWb35WJaTJW3gDoXwt7yJCwQ"}
DELTAS = (30, 50, 70, 100, 150)
todo = collections.defaultdict(set)
for m, v in O.items():
    if m not in L or L[m]["run"] != "R2" or "InitializeMayhemState" in (L[m].get("ixn") or []): continue
    if any(o[3] in LEAD and o[2] and o[0] <= 400 for o in v["outs"]): todo[rp.bucket(m)].add(m)
def work(b):
    tra = rp.read_bucket("R2", b, todo[b]); rows = []
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; st = rp.structure(tr, c)
        for w in LEAD:
            arr = sorted(o[0] for o in O[m]["outs"] if o[3] == w and o[2] and o[0] <= 400)
            if not arr: continue
            a = arr[0]; row = dict(mint=m, bt=c.get("bt"), leader=w, arr_ms=a, signer=c.get("user"), name=c.get("name"), create_sig=c.get("sig"),
                                   leader_ok=A.get(m, {}).get(w, [None])[0], cfg={})
            for d in DELTAS:
                idx, na = rp.place(tr, c, st, O[m]["outs"], a + d)
                if idx < 1: continue
                out = rp.sim(tr, c, st, idx, 0.5, RULES, fill_pen=0.015)
                if not out: continue
                row["cfg"][f"D{d}"] = dict(idx=idx, ahead=na, after_sig=tr[idx - 1]["sig"], pnl=[out[n]["pnl"] for n in NAMES], hold=[out[n]["hold_s"] for n in NAMES])
            if row["cfg"]: rows.append(row)
    return rows
if __name__ == "__main__":
    n = 0
    with gzip.open(OUT, "wt") as f, Pool(14) as p:
        f.write(json.dumps(dict(rules=NAMES, deltas=DELTAS)) + "\n")
        for rows in p.imap_unordered(work, sorted(todo)):
            for r in rows: f.write(json.dumps(r) + "\n"); n += 1
    print("rows", n)
