import json, urllib.request, os, time
RPC = "https://rpc-frankfurt.constant-k.com/?api-key=" + os.environ["CONSTANTK_TOKEN"]
WALLET = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"

def rpc(method, params):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    for attempt in range(5):
        try:
            req = urllib.request.Request(RPC, data=body, headers={"Content-Type":"application/json"})
            r = urllib.request.urlopen(req, timeout=30)
            return json.loads(r.read())["result"]
        except Exception as e:
            time.sleep(1+attempt)
    raise RuntimeError("rpc failed "+method)

all_sigs = []
before = None
while True:
    params = [WALLET, {"limit":1000}]
    if before: params[1]["before"]=before
    res = rpc("getSignaturesForAddress", params)
    if not res: break
    for s in res:
        all_sigs.append({"sig":s["signature"],"slot":s["slot"],"blockTime":s.get("blockTime"),"err":s.get("err") is not None})
    before = res[-1]["signature"]
    print("got", len(all_sigs), "last slot", res[-1]["slot"])
    if len(res)<1000: break

json.dump(all_sigs, open("/root/wallet_sigs.json","w"))
print("TOTAL SIGS", len(all_sigs))
print("errored", sum(1 for s in all_sigs if s["err"]))
