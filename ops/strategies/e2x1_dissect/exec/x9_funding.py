#!/usr/bin/env python3
"""Q5 wallet links (public RPC, gentle). Per wallet: page signatures back to the oldest (cap), fetch the oldest txs -> who funded it;
fetch 2 recent buys + 2 sells (jsonParsed) -> nonce account + nonce authority, tip accounts, fee payer, CU price.
Out: sniper-data/e2x1_dissect/exec/funding.json (raw) ; printed summary in x9.log"""
import sys, json, time
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/recon")
import rpc
rpc.MIN_GAP = 2.0
O = "/home/moiz/sniper-data/e2x1_dissect/exec"
S = json.load(open(f"{O}/sample_sigs.json"))
out = {}
try: out = json.load(open(f"{O}/funding.json"))
except Exception: pass
def gtx(sig):
    r = rpc.call("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])
    return r.get("result")
for w, ss in S.items():
    o = out.get(w) or {}
    if "samples" not in o:
        o["samples"] = {}
        for k in ("buy", "sell"):
            for sig in ss[k]:
                tx = gtx(sig)
                if not tx: continue
                msg = tx["transaction"]["message"]; ixs = msg["instructions"]
                inner = [i for g in (tx["meta"].get("innerInstructions") or []) for i in g["instructions"]]
                nonce = [i.get("parsed", {}).get("info") for i in ixs if i.get("parsed", {}).get("type") == "advanceNonce"]
                tips = [(i["parsed"]["info"]["destination"], i["parsed"]["info"]["lamports"]) for i in ixs + inner
                        if i.get("program") == "system" and i.get("parsed", {}).get("type") == "transfer" and i["parsed"]["info"]["source"] == w]
                keys = [a["pubkey"] for a in msg["accountKeys"]]
                o["samples"][sig] = dict(kind=k, slot=tx["slot"], payer=keys[0], signers=[a["pubkey"] for a in msg["accountKeys"] if a.get("signer")],
                                          nonce=nonce, tips=tips, fee=tx["meta"]["fee"], progs=sorted(set(i.get("programId") for i in ixs)))
                print(w[:8], k, json.dumps(o["samples"][sig])[:400], flush=True)
        out[w] = o; json.dump(out, open(f"{O}/funding.json", "w"))
    if "oldest" not in o:
        before = None; n = 0; last = None
        for page in range(150):
            p = {"limit": 1000}
            if before: p["before"] = before
            r = rpc.call("getSignaturesForAddress", [w, p]).get("result") or []
            n += len(r)
            if not r: break
            last = r[-1]; before = last["signature"]
            if len(r) < 1000: break
        o["nsigs"] = n; o["complete"] = page < 149; o["oldest"] = last
        print(w[:8], "sigs", n, "complete", o["complete"], "oldest", last and time.strftime("%Y-%m-%d %H:%M", time.gmtime((last.get("blockTime") or 0) + 18000)), flush=True)
        out[w] = o; json.dump(out, open(f"{O}/funding.json", "w"))
    if o.get("complete") and "first_tx" not in o and o.get("oldest"):
        tx = gtx(o["oldest"]["signature"])
        if tx:
            msg = tx["transaction"]["message"]; ixs = msg["instructions"]
            inner = [i for g in (tx["meta"].get("innerInstructions") or []) for i in g["instructions"]]
            tr = [i["parsed"]["info"] for i in ixs + inner if i.get("program") == "system" and i.get("parsed", {}).get("type") in ("transfer", "createAccount", "transferWithSeed")]
            o["first_tx"] = dict(sig=o["oldest"]["signature"], payer=msg["accountKeys"][0]["pubkey"], transfers=tr, bt=tx.get("blockTime"))
            print(w[:8], "FIRST", json.dumps(o["first_tx"])[:600], flush=True)
        out[w] = o; json.dump(out, open(f"{O}/funding.json", "w"))
print("done")
