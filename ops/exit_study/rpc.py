import os,json,urllib.request
RPC="https://rpc-frankfurt.constant-k.com/?api-key=" + os.environ["CONSTANTK_TOKEN"] + ""
WALLET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
def call(method,params,tries=5):
    import time
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    last=None
    for t in range(tries):
        try:
            req=urllib.request.Request(RPC,data=body,headers={"Content-Type":"application/json"})
            r=urllib.request.urlopen(req,timeout=40)
            j=json.loads(r.read())
            if "error" in j:
                last=j["error"]; time.sleep(0.3*(t+1)); continue
            return j["result"]
        except Exception as e:
            last=str(e); time.sleep(0.4*(t+1))
    raise RuntimeError(f"{method} failed: {last}")
def gettx(sig):
    return call("getTransaction",[sig,{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed","commitment":"confirmed"}])
def getsigs(addr,before=None,limit=1000):
    o={"limit":limit}
    if before: o["before"]=before
    return call("getSignaturesForAddress",[addr,o])
