#!/usr/bin/env python3
# READ-ONLY. Launches the target ATTEMPTED (failed buy txs) but never filled. Failed txs whose keys hold no *pump mint
# are re-fetched and their keys matched against every mint in our sample. out: attempted.json {mint: n_failed_txs}
import sys, json, collections
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/nob")
from nrpc import rpc
D = "/root/nob/"
xs = [json.loads(l) for l in open(D + "wtx.jsonl")]
mints = {json.loads(l)["mint"] for l in open(D + "ds.jsonl")}
att = collections.Counter()
todo = []
for x in xs:
    if not x["err"]:
        continue
    if x.get("mints"):
        for m in x["mints"]:
            att[m] += 1
    else:
        todo.append(x["sig"])
print("failed txs with pump-suffix mint", sum(att.values()), "to refetch", len(todo), flush=True)


def work(sig):
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    if not isinstance(t, dict) or "transaction" not in t:
        return []
    la = (t.get("meta") or {}).get("loadedAddresses") or {}
    keys = t["transaction"]["message"]["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    return [k for k in keys if k in mints]


with ThreadPoolExecutor(8) as ex:
    res = list(ex.map(work, todo))
hit = 0
for r in res:
    if r:
        hit += 1
    for m in r:
        att[m] += 1
print("refetched", len(todo), "matched a sample mint", hit, flush=True)
json.dump(dict(att), open(D + "attempted.json", "w"))
print("attempted mints total", len(att))
