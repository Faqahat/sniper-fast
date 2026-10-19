import json,urllib.request,os,time
TOK=os.environ["CONSTANTK_TOKEN"]
RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
def rpc(m,p):
    req=urllib.request.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={"content-type":"application/json"})
    for i in range(6):
        try: return json.load(urllib.request.urlopen(req,timeout=25)).get("result")
        except: time.sleep(0.4*(i+1))
    return None
# mint, dev, fill, ATH
T=[("sK49GTrwB72PmeDuRxw2RGPhiP9223fuifn4dtvLv4a",6,1.46,1.44),
("BGTy4q34fdrctpKoki34BgBLV1JiM2B15xFXBEHZjCae",2,1.25,1.22),
("5CHx3zPvavvddtrC75HBHwVCKQuidyqQvf7kgUUWmDbt",6,1.02,1.01),
("C2uwWrTLcM3XiQD3PygpnaEDZpGfp2mh8VTGLuBMpump",3,1.07,1.35),
("ASiqgZPARbaV3SfBcGMXB9Usf3cT1Ggz6xoFzqc6s1gW",6,1.02,1.06),
("8uB7cqv26jXLBeWvygGEmTpAaQG4z3fn266c36xwpump",5,1.91,10.99)]
print("mint      dev fill  ATH    creator    priorSigs  OURFILTER(<=30)")
for mint,dev,fill,ath in T:
    # oldest sig of mint = create tx; fee payer = creator
    sgs=[];before=None
    while True:
        prm=[mint,{"limit":1000}] if before is None else [mint,{"limit":1000,"before":before}]
        r=rpc("getSignaturesForAddress",prm)
        if not r: break
        sgs+=r
        if len(r)<1000: break
        before=r[-1]["signature"]
        if len(sgs)>4000: break
    if not sgs: print(f"  {mint[:8]} no sigs"); continue
    create=sgs[-1]; create_slot=create.get("slot",0)
    tx=rpc("getTransaction",[create["signature"],{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
    creator=None
    if tx:
        for k in tx["transaction"]["message"]["accountKeys"]:
            if k.get("signer"): creator=k["pubkey"]; break
    if not creator: print(f"  {mint[:8]} no creator"); continue
    # count creator prior sigs BEFORE create_slot
    csigs=rpc("getSignaturesForAddress",[creator,{"limit":1000}]) or []
    prior=sum(1 for s in csigs if s.get("slot",0)<create_slot)
    # if >=1000 returned, could be more; note cap
    tag="KEEP" if prior<=30 else "SKIP"
    cap="+" if len(csigs)>=1000 else ""
    print(f"  {mint[:8]} {dev} {fill:.2f} {ath:>5.2f}x  {creator[:10]} {prior:>5}{cap}      {tag}")
