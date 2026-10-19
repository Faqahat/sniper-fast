import os,json,urllib.request,time
RPC="https://rpc-frankfurt.constant-k.com/?api-key=" + os.environ["CONSTANTK_TOKEN"] + ""
WALLET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
def call(method,params,tries=9):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    last=None
    for t in range(tries):
        try:
            req=urllib.request.Request(RPC,data=body,headers={"Content-Type":"application/json"})
            r=urllib.request.urlopen(req,timeout=45)
            j=json.loads(r.read())
            if "error" in j:
                last=j["error"]
                msg=str(last)
                if "429" in msg or "rate" in msg.lower() or "-32019" in msg:
                    time.sleep(0.5*(t+1)); continue
                time.sleep(0.3*(t+1)); continue
            return j["result"]
        except Exception as e:
            last=str(e); time.sleep(0.6*(t+1))
    raise RuntimeError(f"{method} failed: {last}")
def gettx(sig):
    return call("getTransaction",[sig,{"maxSupportedTransactionVersion":1,"encoding":"jsonParsed","commitment":"confirmed"}])
def getsigs(addr,before=None,limit=1000):
    o={"limit":limit}
    if before: o["before"]=before
    return call("getSignaturesForAddress",[addr,o])
