import requests, json, time
RPC=open("/root/snipe_study50/rpc_url.txt").read().strip()
wallets=["4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3",
"9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw","AMDEmVocLtN5ji2gBY7BrmSHEyM5vt6TGszBbg4crMXg",
"dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK","BXB7FF4m5x74ZoUvVHfPJnVBbqWHpMEU1WNUZAL9W8PL",
"G8gTguf7EUwqfwdRhiZ3KCBEgPURVB7LXoDzHif4p6oh","CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J",
"GjsVMaLbPv4ZPL5Yvypzms8iyubXgP16JreJB3FGyGfd","GTfHPpyyoC6X4uxmhLBWzovQCsSMZ8cfckPt8dcxeKcq",
"G9sQPg9Eimkwe72w1xH1tPUc9RFNuK6Ufw5AyWy6j7ob","8ptvshQRZPRaRQBSCRxhHwbJFr6ktyUQ1SATDCLijkBW"]
sess=requests.Session()
def rpc(m,p):
    for _ in range(4):
        try:
            j=sess.post(RPC,json={"jsonrpc":"2.0","id":1,"method":m,"params":p},timeout=40).json()
            if "result" in j: return j["result"]
            time.sleep(0.4)
        except: time.sleep(0.5)
    return None
def oldest(addr):
    before=None;last=None
    for _ in range(15):
        p=[addr,{"limit":1000}]
        if before:p[1]["before"]=before
        r=rpc("getSignaturesForAddress",p)
        if not r:break
        last=r[-1];before=r[-1]["signature"]
        if len(r)<1000:break
    return last
for w in wallets:
    o=oldest(w)
    funder=None;amt=None;t=o.get("blockTime") if o else None
    if o:
        tx=rpc("getTransaction",[o["signature"],{"maxSupportedTransactionVersion":1,"encoding":"json"}])
        if tx:
            msg=tx["transaction"]["message"]
            keys=msg["accountKeys"]
            meta=tx["meta"]
            pre=meta["preBalances"];post=meta["postBalances"]
            # funder = account (not w) with largest balance decrease that isn't fee-only
            widx=keys.index(w) if w in keys else None
            best=None;bestd=0
            for i,k in enumerate(keys):
                if k==w: continue
                d=pre[i]-post[i]
                if d>bestd: bestd=d;best=k
            funder=best;amt=bestd
    print(json.dumps({"w":w,"first_time":t,"funder":funder,"fund_lamports":amt}))
