#!/usr/bin/env python3
"""recon step 2 (read-only, public RPC getTransaction jsonParsed, maxSupportedTransactionVersion 1):
 (a) every signature in D0+D1 NOT in the recordings, (b) boundary txs at W0-24h, W0, W1 (first/last inside + outside neighbours),
 (c) a stratified spot-check sample of recorded txs. Out: gettx.jsonl (resumable)."""
import json, pickle, os, sys, random, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rpc
W0 = 1793113200; W1 = W0 + 86400; WA = W0 - 86400
OUT = "/home/moiz/sniper-data/e2x1_dissect/recon"
S = json.load(open(f"{OUT}/sigs.json")); rec = pickle.load(open(f"{OUT}/rec.pkl", "rb"))
want = []
S_sorted = sorted(S, key=lambda s: (s["slot"], s["signature"]))      # oldest first (index within slot unknown: fix with tx index later)
for b, nm in ((WA, "bA"), (W0, "b0"), (W1, "b1")):
    k = next(i for i, s in enumerate(S_sorted) if s["blockTime"] >= b)
    for s in S_sorted[max(0, k - 3):k + 3]: want.append((s["signature"], nm))
for s in S:
    if s.get("blockTime") and WA <= s["blockTime"] < W1 and s["signature"] not in rec: want.append((s["signature"], "unrec"))
random.seed(1028); cls = collections.defaultdict(list)
for s in S:
    d = rec.get(s["signature"])
    if not d or not (WA <= d["bt"] < W1): continue
    ix = set(d.get("ixn") or [])
    k = ("fail" if d["err"] else "buy" if "BuyExactSolIn" in ix else "sell" if "Sell" in ix else "other")
    cls[k].append(s["signature"])
for k, q in (("buy", 25), ("sell", 25), ("fail", 10), ("other", 6)):
    random.shuffle(cls[k]); want += [(x, "spot_" + k) for x in cls[k][:q]]
done = set()
fn = f"{OUT}/gettx.jsonl"
if os.path.exists(fn):
    for l in open(fn):
        j = json.loads(l)
        if j.get("res") is not None: done.add(j["sig"])
print(len(want), "wanted;", len(done), "done", flush=True)
f = open(fn, "a"); n = 0
for sig, why in want:
    if sig in done: continue
    j = rpc.call("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1, "commitment": "finalized"}])
    f.write(json.dumps({"sig": sig, "why": why, "res": j.get("result"), "err": j.get("error")}) + "\n"); f.flush(); n += 1; done.add(sig)
    if j.get("result") is None: print("NULL", sig[:16], str(j.get("error"))[:120], flush=True)
print("done", n, flush=True)
