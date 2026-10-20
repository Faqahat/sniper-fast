import json,urllib.request,base64,hashlib,struct,os,re,concurrent.futures as cf
TOK=os.environ["CONSTANTK_TOKEN"]
RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
B58="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58dec(s):
    n=0
    for c in s: n=n*58+B58.index(c)
    f=n.to_bytes((n.bit_length()+7)//8,"big"); return b"\x00"*(len(s)-len(s.lstrip("1")))+f
def b58enc(b):
    n=int.from_bytes(b,"big"); o=""
    while n>0: n,r=divmod(n,58); o=B58[r]+o
    return "1"*(len(b)-len(b.lstrip(b"\x00")))+o
P=2**255-19
def oc(yb):
    y=int.from_bytes(yb,"little")&((1<<255)-1)
    if y>=P: return False
    d=(-121665*pow(121666,P-2,P))%P;u=(y*y-1)%P;v=(d*y*y+1)%P;xx=(u*pow(v,P-2,P))%P;x=pow(xx,(P+3)//8,P)
    if (x*x-xx)%P!=0:x=(x*pow(2,(P-1)//4,P))%P
    return (x*x-xx)%P==0
PUMP=b58dec("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
def bc(m):
    s=b"bonding-curve"+b58dec(m)
    for b in range(255,-1,-1):
        h=hashlib.sha256(s+bytes([b])+PUMP+b"ProgramDerivedAddress").digest()
        if not oc(h): return b58enc(h)
def rpc(m,p):
    req=urllib.request.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={"content-type":"application/json"})
    import time
    for i in range(6):
        try: return json.load(urllib.request.urlopen(req,timeout=25)).get("result")
        except: time.sleep(0.4*(i+1))
    return None
def fp(dev): return (30e9+dev)**2/(30e9*1.073e15)
K=30e9*1.073e15
RENT=0  # baseline curve lamports approx; we measure peak real_sol = peak_lamports - min_lamports
def sigs_all(addr):
    out=[];before=None
    while True:
        p=[addr,{"limit":1000}]+([{ "before":before}] if False else [])
        prm=[addr,{"limit":1000}] if before is None else [addr,{"limit":1000,"before":before}]
        r=None
        import time
        for _try in range(5):
            r=rpc("getSignaturesForAddress",prm)
            if r: break
            time.sleep(0.6)
        if not r: break
        out+= [x["signature"] for x in r]
        if len(r)<1000: break
        before=r[-1]["signature"]
        if len(out)>6000: break
    return out
def curve_lamports(sig,curve):
    tx=rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
    if not tx: return None
    try:
        keys=[k["pubkey"] for k in tx["transaction"]["message"]["accountKeys"]]
        if curve in keys:
            i=keys.index(curve); return tx["meta"]["postBalances"][i]
    except: return None
    return None
# load mints+dev
dev={}
for ln in open("/root/sniper-fast/paper_sel.log"):
    m=re.search(r"mint=([1-9A-HJ-NP-Za-km-z]+) dev_buy=(\d+)",ln)
    if m: dev[m.group(1)]=int(m.group(2))
mints=[]
for ln in open("/root/sniper-fast/paper_sel.log"):
    m=re.search(r"PAPER done mint=([1-9A-HJ-NP-Za-km-z]+) .*peak_r=([0-9.]+)",ln)
    if m and m.group(1) not in [x[0] for x in mints]: mints.append((m.group(1),float(m.group(2))))
print(f"scanning {len(mints)} mints")
for mint,pk in mints:
    cv=bc(mint)
    sg=sigs_all(cv)
    lam=[]
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for v in ex.map(lambda s: curve_lamports(s,cv), sg):
            if v: lam.append(v)
    if not lam:
        print(f"{mint}  40s={pk:.2f}  ATH=?  (no tx)"); continue
    base=min(lam); peakreal=max(lam)-base
    vsol=30e9+peakreal
    ath=(vsol*vsol/K)/fp(dev.get(mint,0))
    print(f"{mint}  40s={pk:.2f}x  LIFETIME_ATH={ath:.2f}x  ntx={len(sg)}  peak_realsol={peakreal/1e9:.2f}")
