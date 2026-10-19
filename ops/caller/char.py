import requests, json, sys, time
RPC=open("/root/snipe_study50/rpc_url.txt").read().strip()
SYS="11111111111111111111111111111111"
wallets=["4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3",
"9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw",
"AMDEmVocLtN5ji2gBY7BrmSHEyM5vt6TGszBbg4crMXg",
"dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK",
"BXB7FF4m5x74ZoUvVHfPJnVBbqWHpMEU1WNUZAL9W8PL",
"G8gTguf7EUwqfwdRhiZ3KCBEgPURVB7LXoDzHif4p6oh",
"CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J",
"GjsVMaLbPv4ZPL5Yvypzms8iyubXgP16JreJB3FGyGfd"]
sess=requests.Session()
def rpc(m,p):
    for _ in range(4):
        try:
            j=sess.post(RPC,json={"jsonrpc":"2.0","id":1,"method":m,"params":p},timeout=40).json()
            if "result" in j: return j["result"]
            time.sleep(0.4)
        except: time.sleep(0.5)
    return None
def oldest_sig(addr):
    before=None; last=None; pages=0
    while pages<12:
        p=[addr,{"limit":1000}]
        if before: p[1]["before"]=before
        r=rpc("getSignaturesForAddress",p)
        if not r: break
        last=r[-1]; before=r[-1]["signature"]; pages+=1
        if len(r)<1000: break
    return last,pages
for w in wallets:
    # recent count estimate
    r=rpc("getSignaturesForAddress",[w,{"limit":1000}])
    recent=len(r) if r else 0
    span=None
    if r:
        bt=[s["blockTime"] for s in r if s.get("blockTime")]
        if bt: span=(max(bt)-min(bt))
    old,pages=oldest_sig(w)
    funder=None; fund_amt=None; first_time=None
    if old:
        first_time=old.get("blockTime")
        tx=rpc("getTransaction",[old["signature"],{"maxSupportedTransactionVersion":1,"encoding":"jsonParsed"}])
        if tx:
            msg=tx["transaction"]["message"]
            for ix in msg.get("instructions",[]):
                pi=ix.get("program")
                if ix.get("programId")==SYS and ix.get("parsed",{}).get("type")in("transfer","createAccount"):
                    info=ix["parsed"]["info"]
                    funder=info.get("source") or info.get("lamports")
                    fund_amt=info.get("lamports")
                    break
    print(json.dumps({"wallet":w,"recent_1000_span_s":span,"recent_rate_per_min":(1000/(span/60) if span else None),
                      "oldest_pages":pages,"first_tx_time":first_time,"first_funder":funder,"fund_lamports":fund_amt}))
