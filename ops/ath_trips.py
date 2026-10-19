import json,urllib.request,base64,hashlib,os,time,re,concurrent.futures as cf
TOK=os.environ["CONSTANTK_TOKEN"];RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
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
def fp(d):return (30e9+d)**2/(30e9*1.073e15)
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
# parse FIRE mints + dev + fill from log
cur={};T=[]
for ln in open("/root/arbx-fast/livetrips_dev1.log"):
    m=re.search(r"FIRE slot=(\d+) mint=(\w+) dev_buy=(\d+)",ln)
    if m: cur={"mint":m.group(2),"dev":int(m.group(3))}
    m=re.search(r"floor_px=([0-9.eE+-]+) spend=(\d+)",ln)
    if m: cur["floor"]=float(m.group(1));cur["spend"]=int(m.group(2))
    m=re.search(r"tokens received: (\d+)",ln)
    if m and cur.get("floor"): cur["fill"]=(cur["spend"]/int(m.group(1)))/cur["floor"]
    m=re.search(r"create -> buy\s+(\d+)",ln)
    if m and "fill" in cur: T.append((cur["mint"],cur["dev"],cur["fill"]))
print("mint      dev  fill   lifetimeATH")
for mint,dev,fill in T:
    cv=bc(mint);sg=[x["signature"] for x in sigs(cv)];vals=[]
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for v in ex.map(lambda s:lam(s,cv),sg):
            if v:vals.append(v)
    if not vals: print(f"  {mint[:8]} {dev//10**9} {fill:.2f}x  (no curve)");continue
    peakreal=max(vals)-min(vals);vsol=30e9+peakreal;ath=(vsol*vsol/K)/fp(dev)
    tag="RAN" if ath>fill*1.15 else ("~flat" if ath>0.9*fill else "DUMPED")
    print(f"  {mint[:8]} {dev//10**9} {fill:.2f}x  {ath:.2f}x  {tag} (ntx={len(sg)})")
