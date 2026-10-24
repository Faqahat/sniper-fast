#!/usr/bin/env python3
# READ-ONLY: who are 9qz7cW's counterparties? For its withdrawal destinations (ledger), the other signers of its router
# program 2eFuLSK4 (router_users.json) and its nonce accounts: recent activity (100 latest signatures), balance, and for
# withdrawal destinations the senders into them / where they forward to (from a few of their latest txs).
# Owner's RPC, slow pace (shared RPC). -> relations.json
import sys, os, json, collections, datetime
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
os.environ.setdefault("Q9Z_RATE", "0.5")
from rpcq import rpc
W = "9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw"
LG = json.load(open(os.path.join(HERE, "ledger_q9z.json")))
RU = json.load(open(os.path.join(HERE, "router_users.json")))
dest = sorted({cp for k, cp, n, l in LG["xfers"] if k == "withdrawal" and l >= 1})
co = [w for w in RU["router"] if w != W]
nonces = ["5nUdEsBkw2EcFeAVRzkQjZFohQALawct5d9BKy3wuiNR", "895KeyJjjoZcbkQELHp28dTgQtJBxXH53aND9GffSPK4", "CMXoxdGUWB55pHxJHSaRwGWRCwjqREKxMgYMxK9NBJn9", "DgGakg9ZdUvydA3KLbSuNo4wv3P9YGsgyuyvg4uqNBkk"]
out = {}
def utc(t): return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%m-%d %H:%M") if t else None
for role, ws in (("withdrawal destination", dest), ("router co-user", co), ("nonce account", nonces)):
    for a in ws:
        sg = rpc("getSignaturesForAddress", [a, {"limit": 100}]) or []
        bal = (rpc("getBalance", [a]) or {}).get("value")
        info = dict(role=role, n_recent=len(sg), newest=utc(sg[0]["blockTime"]) if sg else None, oldest_of_100=utc(sg[-1]["blockTime"]) if sg else None,
                    failed=sum(1 for s in sg if s.get("err")), balance=bal / 1e9 if bal is not None else None)
        if role != "nonce account":
            peers = collections.Counter(); w_in = 0
            for s in [s for s in sg if not s.get("err")][:6]:
                tx = rpc("getTransaction", [s["signature"], {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}])
                if not tx: continue
                keys = [k["pubkey"] for k in tx["transaction"]["message"]["accountKeys"]]
                signer = keys[0]
                for ix in list(tx["transaction"]["message"]["instructions"]) + [i for inn in (tx["meta"].get("innerInstructions") or []) for i in inn["instructions"]]:
                    p = ix.get("parsed")
                    if isinstance(p, dict) and p.get("type") == "transfer" and isinstance(p.get("info"), dict) and "lamports" in p["info"]:
                        inf = p["info"]
                        if inf.get("destination") == a: peers["in<-" + inf["source"]] += 1
                        if inf.get("source") == a: peers["out->" + inf["destination"]] += 1
                peers["signer:" + signer] += 1
                w_in += W in keys
            info["peers"] = peers.most_common(10); info["txs_with_9qz7cW"] = w_in
        out[a] = info
        print(role, a, {k: v for k, v in info.items() if k not in ("role", "peers")}, (info.get("peers") or [])[:5], flush=True)
json.dump(out, open(os.path.join(HERE, "relations.json"), "w"), indent=1)
