import sys, json
sys.path.insert(0, "/root/strat")
from srpc import rpc
MA = "TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM"
out = open("/root/strat/anchors.jsonl", "w"); before = None; n = 0
while True:
    prm = {"limit": 1000}
    if before: prm["before"] = before
    r = rpc("getSignaturesForAddress", [MA, prm])
    if not isinstance(r, list) or not r: break
    for s in r[::20]: out.write(json.dumps([s["slot"], s["signature"]]) + "\n")
    before = r[-1]["signature"]; n += 1
    if r[-1]["slot"] < 458575000 or n > 40: break
print("pages", n, "oldest", r[-1]["slot"])
