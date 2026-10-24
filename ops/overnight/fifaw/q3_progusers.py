#!/usr/bin/env python3
# READ-ONLY: who else signs txs that invoke FiFawH's programs, and what DxhpC9c4 (other AsTz payer) runs. Owner RPC.
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import rpcu
out = {}
def tx(sig):
    try: return rpcu.rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}], tries=3)
    except RuntimeError: return None
for p in ["B78FW9mVQT2fDhsW7ChvqTBhZzhCbRrtWYC6K5oa7xuv", "9f2uHxWdaB5nRgjRgsUe4T1LtyzejLNnxuzLfvyMyyxP", "9uGqm7Xh7Vq2EzqTNHVG5Ca4echELK1UjDq9W9Qg5kzF", "2kAA3Bm3npaBzrevWXJfojagG1BEAac4KwayWphYMYQG", "6iemSi2wHcEJoAwEdG69VznRPGHWJr6Y2VRSyj6m9h45"]:
    sigs = rpcu.rpc("getSignaturesForAddress", [p, {"limit": 1000}])
    signers = collections.Counter()
    for s in sigs[::max(1, len(sigs) // 25)][:25]:
        t = tx(s["signature"])
        if t: signers[next((k["pubkey"] for k in t["transaction"]["message"]["accountKeys"] if k.get("signer")), "?")] += 1
    out[p] = dict(n_recent=len(sigs), sample_signers=signers.most_common(5))
    print(p[:8], len(sigs), signers.most_common(5), flush=True)
sigs = rpcu.rpc("getSignaturesForAddress", ["DxhpC9c4kGkYJR34xUrfFeDx9vwb6yoHUMWrTCZybwtH", {"limit": 300}])
progs = collections.Counter()
for s in sigs[:20]:
    t = tx(s["signature"])
    if t: progs.update({ix.get("programId") for ix in t["transaction"]["message"]["instructions"]})
out["DxhpC9c4"] = dict(n_recent=len(sigs), top_programs=progs.most_common(8))
print("DxhpC9c4", len(sigs), progs.most_common(8))
json.dump(out, open("q3_progusers.json", "w"), indent=1)
