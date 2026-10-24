#!/usr/bin/env python3
# READ-ONLY relation probes (owner RPC; URL never printed): funder, program authority, copy follower, tip receiver.
import sys, os, json, collections, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import rpcu
F = json.load(open("funding.json"))
funder = F["first_txs"][0]["signer"][0]
ADDR = {"first funder": funder, "program upgrade authority (6 programs)": "D9VpYFsfLXDoWkUUgYoKBcKdzV745qDajxLsjpNWuaNk",
        "tip receiver AsTz": "AsTzjKRAZ91h6VpiR7Za5EWP8MPYRhfnRxAG4CUXL3oT", "copy follower DeFG8i": "DeFG8i8zoJ3hN155nmvLq266ZVxWmNgRaTz5KQVHfe2S",
        "copy program authority": "3ct4z3q2XHEGTb4Noe3Wh5iySA8e5UZawUXkWAnkfh5J", "HckQ93Xq": "HckQ93Xqjjo8mwt5pNPWvyCTZXQZ858rvzmm7ZRrZg9t"}
out = {}
def tx(sig):
    try: return rpcu.rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}], tries=3)
    except RuntimeError: return None
for what, a in ADDR.items():
    v = rpcu.rpc("getAccountInfo", [a, {"encoding": "base64", "dataSlice": {"offset": 0, "length": 0}}])["value"]
    sigs = rpcu.rpc("getSignaturesForAddress", [a, {"limit": 1000}])
    r = dict(addr=a, owner=v["owner"] if v else None, sol=v["lamports"] / 1e9 if v else None, n_sigs_recent=len(sigs),
             oldest_recent_bt=sigs[-1].get("blockTime") if sigs else None, newest_bt=sigs[0].get("blockTime") if sigs else None)
    # who signs the most recent txs touching it, and SOL transfers to/from it (sample of 30)
    signers = collections.Counter(); xin = collections.Counter(); xout = collections.Counter()
    for s in sigs[:30]:
        t = tx(s["signature"])
        if not t: continue
        keys = t["transaction"]["message"]["accountKeys"]
        signers[next((k["pubkey"] for k in keys if k.get("signer")), "?")] += 1
        for ix in t["transaction"]["message"]["instructions"] + [i for g in (t["meta"].get("innerInstructions") or []) for i in g["instructions"]]:
            p = ix.get("parsed")
            if isinstance(p, dict) and p.get("type") == "transfer" and isinstance(p.get("info"), dict) and "lamports" in p["info"]:
                if p["info"]["destination"] == a: xin[p["info"]["source"]] += p["info"]["lamports"] / 1e9
                if p["info"]["source"] == a: xout[p["info"]["destination"]] += p["info"]["lamports"] / 1e9
    r["top_signers_of_30_recent"] = signers.most_common(6); r["sol_in_by_source"] = [(k, round(v, 4)) for k, v in xin.most_common(6)]
    r["sol_out_by_dest"] = [(k, round(v, 4)) for k, v in xout.most_common(6)]
    out[what] = r
    print(what, json.dumps(r)[:900], flush=True)
json.dump(out, open("q3_rel.json", "w"), indent=1)
