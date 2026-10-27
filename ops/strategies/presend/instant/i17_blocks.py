#!/usr/bin/env python3
# INSTANT-BOTS study, step 17 (read-only RPC, cached): block sizes (all txs incl. votes = the collector's index space) of the probe's
# instant-event slots -> the average leader time per block position (slot ~212 ms / block size), to translate a block gap into ms.
# usage: python3 -I i17_blocks.py probe_map.json OUT.json
import sys, json
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/instant")
import rpc_ro as R
pm = json.load(open(sys.argv[1])); out = []
for x in pm:
    b = R.rpc("getBlock", [x["slot"], {"encoding": "json", "transactionDetails": "signatures", "maxSupportedTransactionVersion": 0, "rewards": False, "commitment": "confirmed"}])
    n = len(b["signatures"]) if b else None
    inst = [(r["user"][:8], r["gap"]) for r in x["tape"] if r["instant"]]
    out.append(dict(slot=x["slot"], client=x["client"], n_txs=n, dump_idx=x["idx"], inst=inst))
    if n: print(f"{x['slot']} {x['client']:8s} block {n} txs, dump at {x['idx']} ({100 * x['idx'] / n:.0f}% into the block); avg {212 / n:.3f} ms per position -> "
                + ", ".join(f"{u} +{g} = ~{g * 212 / n:.1f} ms" for u, g in inst), flush=True)
json.dump(out, open(sys.argv[2], "w"), indent=1)
print("rpc calls", R.calls())
