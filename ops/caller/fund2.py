import requests, json, time
RPC=open("/root/snipe_study50/rpc_url.txt").read().strip()
SYS="11111111111111111111111111111111"
wallets=["4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3",
"AMDEmVocLtN5ji2gBY7BrmSHEyM5vt6TGszBbg4crMXg","dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK",
"BXB7FF4m5x74ZoUvVHfPJnVBbqWHpMEU1WNUZAL9W8PL","G8gTguf7EUwqfwdRhiZ3KCBEgPURVB7LXoDzHif4p6oh",
"CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J","GjsVMaLbPv4ZPL5Yvypzms8iyubXgP16JreJB3FGyGfd",
"GTfHPpyyoC6X4uxmhLBWzovQCsSMZ8cfckPt8dcxeKcq","G9sQPg9Eimkwe72w1xH1tPUc9RFNuK6Ufw5AyWy6j7ob",
"8ptvshQRZPRaRQBSCRxhHwbJFr6ktyUQ1SATDCLijkBW"]
sess=requests.Session()
def rpc(m,p):
    for _ in range(4):
        try:
            j=sess.post(RPC,json={"jsonrpc":"2.0","id":1,"method":m,"params":p},timeout=40).json()
            if "result" in j: return j["result"]
            time.sleep(0.4)
        except: time.sleep(0.5)
    return None
def all_sigs_oldest_first(addr,maxpages=20):
    before=None;allr=[]
    for _ in range(maxpages):
        p=[addr,{"limit":1000}]
        if before:p[1]["before"]=before
        r=rpc("getSignaturesForAddress",p)
        if not r:break
        allr+=r;before=r[-1]["signature"]
        if len(r)<1000:break
    return allr
for w in wallets:
    sigs=all_sigs_oldest_first(w)
    if not sigs:
        print(json.dumps({"w":w,"err":"nosigs"}));continue
    # oldest = last entries; scan oldest 6 txs for incoming SOL transfer to w
    tail=sigs[-6:]
    funder=None;amt=0;t=sigs[-1].get("blockTime")
    for s in reversed(tail):  # oldest first
        tx=rpc("getTransaction",[s["signature"],{"maxSupportedTransactionVersion":1,"encoding":"jsonParsed"}])
        if not tx:continue
        msg=tx["transaction"]["message"]
        found=False
        for ix in msg.get("instructions",[]):
            if ix.get("programId")==SYS:
                pr=ix.get("parsed",{})
                if pr.get("type")in("transfer","transferChecked"):
                    info=pr["info"]
                    if info.get("destination")==w:
                        funder=info.get("source");amt=info.get("lamports");found=True;break
        if found:break
    print(json.dumps({"w":w,"ntx_seen":len(sigs),"first_time":t,"incoming_funder":funder,"fund_lamports":amt}))
