import json,urllib.request,base64,hashlib,os,time,concurrent.futures as cf
TOK=os.environ["CONSTANTK_TOKEN"]
RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
B58="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58dec(s):
    n=0
    for c in s:n=n*58+B58.index(c)
    return n.to_bytes((n.bit_length()+7)//8,"big")
def b58enc(b):
    n=int.from_bytes(b,"big");o=""
    while n>0:n,r=divmod(n,58);o=B58[r]+o
    return "1"*(len(b)-len(b.lstrip(b"\x00")))+o
P=2**255-19
def oc(yb):
    y=int.from_bytes(yb,"little")&((1<<255)-1)
    if y>=P:return False
    d=(-121665*pow(121666,P-2,P))%P;u=(y*y-1)%P;v=(d*y*y+1)%P;xx=(u*pow(v,P-2,P))%P;x=pow(xx,(P+3)//8,P)
    if (x*x-xx)%P!=0:x=(x*pow(2,(P-1)//4,P))%P
    return (x*x-xx)%P==0
PUMP=b58dec("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
def bc(m):
    s=b"bonding-curve"+b58dec(m)
    for b in range(255,-1,-1):
        h=hashlib.sha256(s+bytes([b])+PUMP+b"ProgramDerivedAddress").digest()
        if not oc(h):return b58enc(h)
def rpc(m,p):
    req=urllib.request.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={"content-type":"application/json"})
    for i in range(6):
        try:return json.load(urllib.request.urlopen(req,timeout=25)).get("result")
        except:time.sleep(0.4*(i+1))
    return None
def fp(dev):return (30e9+dev)**2/(30e9*1.073e15)
K=30e9*1.073e15
def sigs(cv):
    out=[];before=None
    while True:
        prm=[cv,{"limit":1000}] if before is None else [cv,{"limit":1000,"before":before}]
        r=None
        for _ in range(5):
            r=rpc("getSignaturesForAddress",prm)
            if r:break
            time.sleep(0.6)
        if not r:break
        out+=r
        if len(r)<1000:break
        before=r[-1]["signature"]
        if len(out)>5000:break
    return out
def lam(sig,cv):
    tx=rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
    if not tx:return None
    try:
        kk=[k["pubkey"] for k in tx["transaction"]["message"]["accountKeys"]]
        if cv in kk:return tx["meta"]["postBalances"][kk.index(cv)]
    except:return None
# mint, dev_sol, fill
T=[("sK49GTrwB72PmeDuRxw2RGPhiP9223fuifn4dtvLv4a",6,1.46),
("BGTy4q34fdrctpKoki34BgBLV1JiM2B15xFXBEHZjCae",2,1.25),
("5CHx3zPvavvddtrC75HBHwVCKQuidyqQvf7kgUUWmDbt",6,1.02),
("C2uwWrTLcM3XiQD3PygpnaEDZpGfp2mh8VTGLuBMpump",3,1.07),
("ASiqgZPARbaV3SfBcGMXB9Usf3cT1Ggz6xoFzqc6s1gW",6,1.02),
("8uB7cqv26jXLBeWvygGEmTpAaQG4z3fn266c36xwpump",5,1.91)]
print("mint      dev fill   lifetimeATH  verdict")
for mint,dev,fill in T:
    cv=bc(mint); sg=[x["signature"] for x in sigs(cv)]
    vals=[]
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for v in ex.map(lambda s:lam(s,cv),sg):
            if v:vals.append(v)
    if not vals:
        print(f"  {mint[:8]} {dev} {fill:.2f}x  NO CURVE (non-pump?)"); continue
    base=min(vals); peakreal=max(vals)-base; vsol=30e9+peakreal
    ath=(vsol*vsol/K)/fp(dev*1e9)
    # did our fill profit? if ATH > fill -> upside existed
    verdict="RAN past our fill" if ath>fill*1.05 else ("~flat" if ath>0.9*fill else "DUMPED")
    print(f"  {mint[:8]} {dev} {fill:.2f}x  {ath:.2f}x       {verdict} (ntx={len(sg)})")
