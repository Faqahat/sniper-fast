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
    for i in range(5):
        try:return json.load(urllib.request.urlopen(req,timeout=20)).get("result")
        except:time.sleep(0.3*(i+1))
    return None
def fp(d):return (30e9+d)**2/(30e9*1.073e15)
K=30e9*1.073e15
def sigs(cv):
    out=[];before=None;pg=0
    while pg<5:
        prm=[cv,{"limit":1000}] if before is None else [cv,{"limit":1000,"before":before}]
        r=rpc("getSignaturesForAddress",prm)
        if not r:break
        out+=r;pg+=1
        if len(r)<1000:break
        before=r[-1]["signature"]
    return out
def lam(sig,cv):
    tx=rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
    if not tx:return None
    try:
        kk=[k["pubkey"] for k in tx["transaction"]["message"]["accountKeys"]]
        if cv in kk:return tx["meta"]["postBalances"][kk.index(cv)]
    except:return None
# parse our bought mints + dev + fill
T=[]
cur={}
for ln in open("/root/arbx-fast/live_bl_rt.log"):
    m=re.search(r"FIRE slot=\d+ mint=(\w+) dev_buy=(\d+)",ln)
    if m: cur={"mint":m.group(1),"dev":int(m.group(2))}
    m=re.search(r"floor_px=([0-9.eE+-]+) spend=(\d+)",ln)
    if m: cur["floor"]=float(m.group(1));cur["spend"]=int(m.group(2))
    m=re.search(r"tokens received: (\d+)",ln)
    if m and cur.get("floor"): cur["fill"]=(cur["spend"]/int(m.group(1)))/cur["floor"]
    m=re.search(r"create -> buy\s+(\d+)",ln)
    if m and "fill" in cur: T.append((cur["mint"],cur["dev"],cur["fill"]))
print("mint       dev  ourfill  lifetimeATH")
runners=0
for mint,dev,fill in T:
    cv=bc(mint);sg=[x["signature"] for x in sigs(cv)];vals=[]
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for v in ex.map(lambda s:lam(s,cv),sg):
            if v:vals.append(v)
    if not vals: print("  %s dev=%.1f %.2fx  ?"%(mint[:10],dev/1e9,fill));continue
    peak=(30e9+(max(vals)-min(vals)));ath=(peak*peak/K)/fp(dev)
    if ath>=1.5: runners+=1
    tag=" RUNNER" if ath>=1.5 else ""
    print("  %s dev=%.1f %.2fx  %.2fx%s"%(mint[:10],dev/1e9,fill,ath,tag))
print("\nrunners(ATH>=1.5x): %d/%d"%(runners,len(T)))
