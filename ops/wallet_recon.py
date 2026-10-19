import json,urllib.request,os,time,concurrent.futures as cf
TOK=os.environ["CONSTANTK_TOKEN"]
RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
W="CUQqcZZGr8QLjEzMpxUZyiZirBujE2Y9yZDyfCRw1CAB"
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMPAMM="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
def rpc(m,p):
    req=urllib.request.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={"content-type":"application/json"})
    for i in range(5):
        try: return json.load(urllib.request.urlopen(req,timeout=25)).get("result")
        except: time.sleep(0.4*(i+1))
    return None
bal=rpc("getBalance",[W])
print("SOL balance:", (bal.get("value",0)/1e9) if bal else "?")
# all sigs
sigs=[];before=None
while True:
    prm=[W,{"limit":1000}] if before is None else [W,{"limit":1000,"before":before}]
    r=rpc("getSignaturesForAddress",prm)
    if not r: break
    sigs+=r
    if len(r)<1000: break
    before=r[-1]["signature"]
    if len(sigs)>8000: break
print("total sigs:", len(sigs))
if sigs:
    import datetime
    t_new=sigs[0].get("blockTime");t_old=sigs[-1].get("blockTime")
    if t_new and t_old:
        print("active span:", datetime.datetime.utcfromtimestamp(t_old), "->", datetime.datetime.utcfromtimestamp(t_new))
# analyze a recent window of txs: SOL delta of W, pump vs pumpAMM, buy/sell
def analyze(sig):
    tx=rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
    if not tx or not tx.get("meta"): return None
    try:
        keys=[k["pubkey"] for k in tx["transaction"]["message"]["accountKeys"]]
        progs=set()
        for ix in tx["transaction"]["message"]["instructions"]:
            if "programId" in ix: progs.add(ix["programId"])
        for inner in tx["meta"].get("innerInstructions",[]):
            for ix in inner["instructions"]:
                if "programId" in ix: progs.add(ix["programId"])
        wi=keys.index(W) if W in keys else None
        sol_d=(tx["meta"]["postBalances"][wi]-tx["meta"]["preBalances"][wi])/1e9 if wi is not None else 0
        fee=tx["meta"]["fee"]/1e9
        onpump=PUMP in progs; onamm=PUMPAMM in progs
        return (tx.get("blockTime"),sol_d,fee,onpump,onamm)
    except: return None
sample=sigs[:400]
res=[]
with cf.ThreadPoolExecutor(max_workers=8) as ex:
    for v in ex.map(lambda s: analyze(s["signature"]), sample):
        if v: res.append(v)
pump_tx=[r for r in res if r[3] or r[4]]
print(f"\nsample={len(res)} recent txs; pump/pumpAMM-related={len(pump_tx)}")
buys=[r for r in pump_tx if r[1]<-0.001]  # net SOL out = buy
sells=[r for r in pump_tx if r[1]>0.001]  # net SOL in = sell
print(f"net-SOL-out (buys): {len(buys)}  net-SOL-in (sells): {len(sells)}")
print(f"total SOL out: {sum(r[1] for r in buys):.2f}  total SOL in: {sum(r[1] for r in sells):.2f}  net(incl fees): {sum(r[1] for r in pump_tx):.2f}")
avg_buy=sum(-r[1] for r in buys)/len(buys) if buys else 0
print(f"avg buy size: {avg_buy:.3f} SOL   total fees(sample): {sum(r[2] for r in res):.3f}")
