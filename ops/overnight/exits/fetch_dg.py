#!/usr/bin/env python3
# READ-ONLY: fetch DGmspi SOL-quoted trade txs that are not cached yet (only those inside the CK history window).
import sys, os, json, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rpc import get_tx
L = "/home/moiz/sniper/ops/snipers/ledger"; OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "txc_DGmspi")
D = json.load(open(f"{L}/ledger_DGmspi.json"))
have = set(os.listdir(f"{L}/txc_DGmspi")) | set(os.listdir(OUT))
need = [x for x in D["txs"] if not x.get("missing") and not x.get("err") and x["trades"] and x["slot"] > 459280000 and x["sig"] + ".json" not in have]
print("to fetch", len(need), flush=True)
def one(x):
    t = get_tx(x["sig"])
    if t: json.dump(t, open(os.path.join(OUT, x["sig"] + ".json"), "w")); return 1
    return 0
with cf.ThreadPoolExecutor(6) as ex: n = sum(ex.map(one, need))
print("fetched", n, "of", len(need), flush=True)
