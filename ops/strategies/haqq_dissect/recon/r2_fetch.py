#!/usr/bin/env python3
"""recon step 2 (read-only, public RPC): getTransaction (jsonParsed, maxSupportedTransactionVersion 1: some of his txs are v1) for
  (a) every in-window signature NOT in the recordings,
  (b) a stratified random spot-check sample of recorded txs (>= 50; buy+init, buy, sell, failed, close),
  (c) the boundary txs: first and last in the window and their outside neighbours.
Out: recon/gettx.jsonl (one {"sig", "why", "res"} per line; resumable)."""
import json, pickle, os, sys, random, collections
sys.path.insert(0, os.path.dirname(__file__))
import rpc
W0, W1 = 1793038500, 1793124900
OUT = "/home/moiz/sniper-data/haqq_dissect/recon"
S = json.load(open(f"{OUT}/sigs.json"))
rec = pickle.load(open(f"{OUT}/rec.pkl", "rb"))
inw = [s for s in S if W0 <= s["blockTime"] < W1]
want = []
for s in inw:
    if s["signature"] not in rec: want.append((s["signature"], "unrec"))
# boundary: list is newest first; inw[-1] = first tx in window, inw[0] = last
pos0 = S.index(inw[-1]); pos1 = S.index(inw[0])
want += [(inw[-1]["signature"], "first"), (inw[0]["signature"], "last"), (S[pos0 + 1]["signature"], "before_first"), (S[pos1 - 1]["signature"], "after_last")]
# spot-check sample
random.seed(20261028)
cls = collections.defaultdict(list)
for s in inw:
    d = rec.get(s["signature"])
    if not d: continue
    ix = set(d.get("ixn") or [])
    k = ("fail" if d["err"] else "close" if ix == {"CloseAccount"} else "buy_init" if "InitializeAccount3" in ix and any(x.startswith("Buy") for x in ix)
         else "buy" if any(x.startswith("Buy") for x in ix) else "sell" if any(x.startswith("Sell") for x in ix) else "other")
    cls[k].append(s["signature"])
quota = {"buy_init": 20, "buy": 20, "sell": 25, "fail": 12, "close": 5, "other": 5}
for k, v in cls.items():
    random.shuffle(v); want += [(x, "spot_" + k) for x in v[:quota.get(k, 5)]]
want = [w for w in want if w[1] != "unrec"] + [w for w in want if w[1] == "unrec"]     # boundary + spot-check first
done = set()
SH = int(sys.argv[1]) if len(sys.argv) > 1 else 0; NSH = int(sys.argv[2]) if len(sys.argv) > 2 else 1
fn = f"{OUT}/gettx.jsonl" if SH == 0 else f"{OUT}/gettx_{SH}.jsonl"
import glob
for fx in glob.glob(f"{OUT}/gettx*.jsonl"):
    for l in open(fx):
        j = json.loads(l)
        if j.get("res") is not None: done.add(j["sig"] + "|" + j["why"])
print(len(want), "wanted;", len(done), "already done", flush=True)
f = open(fn, "a"); n = 0
for k, (sig, why) in enumerate(want):
    if k % NSH != SH: continue
    if sig + "|" + why in done: continue
    j = rpc.call("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1, "commitment": "finalized"}])
    f.write(json.dumps({"sig": sig, "why": why, "res": j.get("result"), "err": j.get("error")}) + "\n"); f.flush(); n += 1
    if j.get("result") is None: print("NULL", sig[:16], str(j.get("error"))[:120], flush=True)
    if n % 50 == 0: print(n, "fetched", flush=True)
print("done", n, flush=True)
