# REVIEW: self-test of sigcheck.py's verifier on a real landed tx signed by the wallet (from the chain)
import sys, json, base64
sys.path.insert(0, "/root/indep"); sys.path.insert(0, "/root/review")
from common import rpc
s = rpc("getSignaturesForAddress", ["FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS", {"limit": 5}])
out = []
for x in s:
    t = rpc("getTransaction", [x["signature"], {"encoding": "base64", "maxSupportedTransactionVersion": 0}])
    if t: out.append(json.dumps({"raw": t["transaction"][0]}))
open("/root/review/chain_sigs.jsonl", "w").write("\n".join(out) + "\n")
print(len(out), "chain txs saved")
