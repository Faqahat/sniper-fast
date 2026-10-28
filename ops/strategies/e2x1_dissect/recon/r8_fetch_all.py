#!/usr/bin/env python3
"""recon step 8 (read-only, public RPC): getTransaction for every successful own buy/sell in D1 (+ D0 if time allows) to read
fields the recorder does not keep: durable-nonce account, instruction data (slippage args), account list. Resumable. Out: gettx_all.jsonl"""
import json, pickle, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rpc
OUT = "/home/moiz/sniper-data/e2x1_dissect/recon"
W0 = 1793113200; W1 = W0 + 86400; WA = W0 - 86400
rows = pickle.load(open(f"{OUT}/tx.pkl", "rb"))
# public RPC is ~0.15 tx/s here (shared IP) -> a stratified SAMPLE: 70 D1 lots per age band (A <30 s, B 30-120 s, C >120 s), buy + all sells
import random
L = pickle.load(open(f"{OUT}/lots.pkl", "rb")); Fe = pickle.load(open(f"{OUT}/feat.pkl", "rb"))
random.seed(7); want = []
for lo, hi in ((0, 30), (30, 120), (120, 10**9)):
    c = [l for l in L if l["day"] == "D1" and not l["is_open"] and Fe[l["lot_id"]]["age_s"] is not None and lo <= Fe[l["lot_id"]]["age_s"] < hi]
    for l in random.sample(c, 70): want += [l["buy_sig"]] + [x[0] for x in l["sells"]]
done = set()
for fn in (f"{OUT}/gettx.jsonl", f"{OUT}/gettx_all.jsonl"):
    if os.path.exists(fn):
        for l in open(fn):
            j = json.loads(l)
            if j.get("res"): done.add(j["sig"])
print(len(want), "wanted", len(done & set(want)), "done", flush=True)
f = open(f"{OUT}/gettx_all.jsonl", "a"); n = 0
for sig in want:
    if sig in done: continue
    j = rpc.call("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1, "commitment": "finalized"}])
    f.write(json.dumps({"sig": sig, "why": "all", "res": j.get("result")}) + "\n"); f.flush(); n += 1
    if n % 200 == 0: print(n, flush=True)
print("done", n)
