#!/usr/bin/env python3
# READ-ONLY probes: (1) leaders of the slots where FiFawH sent priority-fee-only ("CB-only") txs; (2) the AsTz tip
# receiver and the CB-extra accounts: owner program / balance / a few recent signers. Owner RPC URL never printed.
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import rpcu
L = json.load(open("ledger_FiFawH.json")); W = rpcu.W
cbonly = [x for x in L if x["signer"] == W and not x["err"] and set(x["top"]) == {"ComputeBudget111111111111111111111111111111"}]
out = {"cbonly": []}
for x in cbonly:
    ld = rpcu.rpc("getSlotLeaders", [x["slot"], 1])[0]
    out["cbonly"].append(dict(sig=x["sig"], slot=x["slot"], bt=x["bt"], fee=x["fee"] / 1e9, leader=ld))
    print("CB-only", x["sig"][:16], x["slot"], x["bt"], f"fee {x['fee']/1e9:.4f}", "leader", ld)
# leaders of the slots of the 0.93-tip noop buys and of a sample of FiFawH's landed buys (who includes them?)
def acct(a):
    v = rpcu.rpc("getAccountInfo", [a, {"encoding": "base64", "dataSlice": {"offset": 0, "length": 0}}])["value"]
    return dict(owner=v["owner"], lamports=v["lamports"] / 1e9, exe=v["executable"]) if v else None
cbx = collections.Counter(a for x in L if x["signer"] == W for a in x["cb_extra"])
print("CB-extra accounts: distinct", len(cbx), "top", cbx.most_common(5))
for a in ["AsTzjKRAZ91h6VpiR7Za5EWP8MPYRhfnRxAG4CUXL3oT"] + [a for a, _ in cbx.most_common(3)]:
    info = acct(a)
    sigs = rpcu.rpc("getSignaturesForAddress", [a, {"limit": 25}])
    print(a, info, "recent sigs", len(sigs))
    out.setdefault("accts", {})[a] = dict(info=info, n_recent=len(sigs), recent=[s["signature"] for s in sigs[:25]])
json.dump(out, open("q1_rpc_probe.json", "w"), indent=1)
