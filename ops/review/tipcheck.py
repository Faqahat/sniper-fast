# REVIEW READ-ONLY: are the tip accounts our buys pay real, in-use tip accounts? (Jito: the block engine's live list;
# all: recent incoming activity on chain = other searchers tipping them)
import sys, json, time, base64, urllib.request
sys.path.insert(0, "/root/indep")
from common import rpc
rows = [json.loads(l) for l in open(sys.argv[1])]
eng = json.load(open(sys.argv[2]))
used = {}
for r in rows:
    raw = base64.b64decode(r["raw"])
for r in rows:
    for a, l in r["tips"]: used.setdefault(a, set()).add(l)
req = urllib.request.Request("https://frankfurt.mainnet.block-engine.jito.wtf/api/v1/getTipAccounts", data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getTipAccounts", "params": []}).encode(), headers={"content-type": "application/json"})
jl = set(json.load(urllib.request.urlopen(req, timeout=10))["result"])
print("jito block engine getTipAccounts:", len(jl), "accounts; engine list == live list:", set(eng["jito"]) == jl)
now = time.time()
fam = {a: k for k, v in eng.items() for a in v}
for a in sorted(used, key=lambda x: fam.get(x, "?")):
    s = rpc("getSignaturesForAddress", [a, {"limit": 50}], tries=2, timeout=20)
    n = len(s) if isinstance(s, list) else 0
    recent = sum(1 for x in s if x.get("blockTime") and now - x["blockTime"] < 3600) if n else 0
    ok_ = sum(1 for x in s if x.get("err") is None) if n else 0
    print(f"  {fam.get(a,'?'):10} {a} lamports={sorted(used[a])} last50: {ok_} ok, {recent} in the last hour" + (" (in Jito live list)" if a in jl else ""))
