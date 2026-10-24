#!/usr/bin/env python3
# READ-ONLY: every recent transaction (up to 100) of 9qz7cW's withdrawal destinations, to see who else pays into them and
# where they send (cluster membership). Owner's RPC, slow pace. -> treasury.json
import sys, os, json, collections, datetime
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
os.environ.setdefault("Q9Z_RATE", "0.6")
from rpcq import rpc
W = "9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw"
DEST = ["9BhkaAybG824w5Hk2A1Np22ZwYN74f6kisJtLEK9C6Ns", "GBXnrHXZENJZrpCHjSX177XR78e9Pmjmawp2ZukiJcv6", "3UEJbmddD8zWDKUKZQieGQwTEXrHhyy3MXbsNk6pZFnq"]
utc = lambda t: datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%m-%d %H:%M") if t else None
out = {}
for a in DEST:
    sg = rpc("getSignaturesForAddress", [a, {"limit": 100}]) or []
    flows = collections.defaultdict(lambda: [0, 0.0]); first = None
    for s in sg:
        if s.get("err"): continue
        tx = rpc("getTransaction", [s["signature"], {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}])
        if not tx: continue
        for ix in list(tx["transaction"]["message"]["instructions"]) + [i for inn in (tx["meta"].get("innerInstructions") or []) for i in inn["instructions"]]:
            p = ix.get("parsed")
            if isinstance(p, dict) and p.get("type") in ("transfer", "transferWithSeed") and isinstance(p.get("info"), dict) and "lamports" in p["info"]:
                inf = p["info"]
                if inf.get("destination") == a: x = flows["in<-" + inf["source"]]; x[0] += 1; x[1] += inf["lamports"] / 1e9
                if inf.get("source") == a: x = flows["out->" + inf["destination"]]; x[0] += 1; x[1] += inf["lamports"] / 1e9
        first = s
    out[a] = dict(n=len(sg), span=(utc(sg[-1]["blockTime"]) if sg else None, utc(sg[0]["blockTime"]) if sg else None), more=len(sg) == 100,
                  flows=sorted(([k, v[0], round(v[1], 3)] for k, v in flows.items()), key=lambda r: -r[2]))
    print(a, out[a]["n"], out[a]["span"], out[a]["flows"][:8], flush=True)
json.dump(out, open(os.path.join(HERE, "treasury.json"), "w"), indent=1)
