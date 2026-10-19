import json,urllib.request,os,time,base64,struct
URL="https://rpc-frankfurt.constant-k.com/?api-key="+os.environ["CONSTANTK_TOKEN"]
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
_A="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58enc(b):
    n=int.from_bytes(b,"big"); s=""
    while n>0: n,r=divmod(n,58); s=_A[r]+s
    pad=0
    for c in b:
        if c==0: pad+=1
        else: break
    return "1"*pad+s
def rpc(method,params,retry=6):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    for i in range(retry):
        try:
            req=urllib.request.Request(URL,data=body,headers={"Content-Type":"application/json"})
            r=urllib.request.urlopen(req,timeout=40).read()
            j=json.loads(r)
            if "error" in j and ("429" in str(j["error"]) or "rate" in str(j["error"]).lower()):
                time.sleep(1.5*(i+1)); continue
            return j
        except Exception as e:
            if "429" in str(e): time.sleep(2.0*(i+1)); continue
            time.sleep(0.8*(i+1))
    return {"error":"exhausted"}
def sigs(addr,limit=1000,before=None,until=None):
    p={"limit":limit}
    if before:p["before"]=before
    if until:p["until"]=until
    return rpc("getSignaturesForAddress",[addr,p]).get("result",[])
def tx(sig):
    return rpc("getTransaction",[sig,{"encoding":"jsonParsed","maxSupportedTransactionVersion":0}]).get("result")
def acct(addr):
    return rpc("getAccountInfo",[addr,{"encoding":"base64"}]).get("result")
def parse_curve(addr):
    a=acct(addr)
    if not a or not a.get("value"): return None
    data=base64.b64decode(a["value"]["data"][0])
    if len(data)<81: return None
    vt,vs,rt,rs,ts=struct.unpack_from("<QQQQQ",data,8)
    return {"virt_tok":vt,"virt_sol":vs/1e9,"real_tok":rt,"real_sol":rs/1e9,"supply":ts,
            "complete":bool(data[48]),"creator":b58enc(data[49:81])}
if __name__=="__main__":
    import sys
    print(json.dumps(rpc(sys.argv[1],json.loads(sys.argv[2])))[:300])
