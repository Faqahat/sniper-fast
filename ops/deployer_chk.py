import json,urllib.request,os,time,re
TOK=os.environ["CONSTANTK_TOKEN"];RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
def rpc(m,p):
    req=urllib.request.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={"content-type":"application/json"})
    for i in range(6):
        try:return json.load(urllib.request.urlopen(req,timeout=25)).get("result")
        except:time.sleep(0.4*(i+1))
    return None
# parse our 14 bought mints
mints=[]
for ln in open("/root/sniper-fast/livetrips_dev1.log"):
    m=re.search(r"FIRE slot=\d+ mint=(\w+) dev_buy=(\d+)",ln)
    if m and m.group(1) not in [x[0] for x in mints]: mints.append((m.group(1),int(m.group(2))))
def count_sigs(addr,cap=60000):
    tot=0;before=None
    while True:
        prm=[addr,{"limit":1000}] if before is None else [addr,{"limit":1000,"before":before}]
        r=rpc("getSignaturesForAddress",prm)
        if not r:break
        tot+=len(r)
        if len(r)<1000:break
        before=r[-1]["signature"]
        if tot>=cap:return f"{tot}+"
    return str(tot)
print("our bought token -> its DEPLOYER (create-tx fee payer) and that deployer's total tx count")
seen={}
for mint,dev in mints:
    sgs=rpc("getSignaturesForAddress",[mint,{"limit":1000}]) or []
    if not sgs: print(f"  {mint[:8]} no sigs");continue
    # oldest = create
    before=None;last=sgs
    while len(last)==1000:
        before=last[-1]["signature"];last=rpc("getSignaturesForAddress",[mint,{"limit":1000,"before":before}]) or []
        if last: sgs=last
    create=sgs[-1]
    tx=rpc("getTransaction",[create["signature"],{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
    dep=None
    if tx:
        for k in tx["transaction"]["message"]["accountKeys"]:
            if k.get("signer"): dep=k["pubkey"];break
    if dep not in seen: seen[dep]=count_sigs(dep) if dep else "?"
    print(f"  {mint[:8]} dev={dev//10**9}SOL  deployer={dep[:12] if dep else '?'}  deployer_txs={seen.get(dep)}")
print("\nunique deployers:",{d[:10]:c for d,c in seen.items()})
