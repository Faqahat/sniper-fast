import json,urllib.request,base64,hashlib,os,re,concurrent.futures as cf,time
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
    for i in range(6):
        try: return json.load(urllib.request.urlopen(req,timeout=25)).get("result")
        except: time.sleep(0.4*(i+1))
    return None
def fp(dev): return (30e9+dev)**2/(30e9*1.073e15)
K=30e9*1.073e15
def sigs_all(cv):
    out=[];before=None
    while True:
        prm=[cv,{"limit":1000}] if before is None else [cv,{"limit":1000,"before":before}]
        r=None
        for _ in range(5):
            r=rpc("getSignaturesForAddress",prm)
            if r: break
            time.sleep(0.6)
        if not r: break
        out+=r
        if len(r)<1000: break
        before=r[-1]["signature"]
        if len(out)>6000: break
    return out
def tx_point(sig,cv):
    tx=rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
    if not tx: return None
    try:
        keys=[k["pubkey"] for k in tx["transaction"]["message"]["accountKeys"]]
        if cv in keys:
            i=keys.index(cv); return (tx.get("blockTime",0), tx["meta"]["postBalances"][i])
    except: return None
    return None
dev={}
for ln in open("/root/arbx-fast/paper_sel.log"):
    m=re.search(r"mint=([1-9A-HJ-NP-Za-km-z]+) dev_buy=(\d+)",ln)
    if m: dev[m.group(1)]=int(m.group(2))
mints=[]
for ln in open("/root/arbx-fast/paper_sel.log"):
    m=re.search(r"PAPER done mint=([1-9A-HJ-NP-Za-km-z]+) .*peak_r=([0-9.]+)",ln)
    if m and m.group(1) not in mints: mints.append(m.group(1))

CACHE="/root/series_cache.json"
cache=json.load(open(CACHE)) if os.path.exists(CACHE) else {}
for mint in mints:
    if mint in cache: continue
    cv=bc(mint)
    sg=[x["signature"] for x in sigs_all(cv)]
    pts=[]
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for v in ex.map(lambda s: tx_point(s,cv), sg):
            if v and v[0]: pts.append(v)
    cache[mint]=pts
    json.dump(cache,open(CACHE,"w"))
    print(f"cached {mint[:10]} n={len(pts)}",flush=True)

# build forward series + entry
def build(mint):
    pts=cache.get(mint,[])
    if len(pts)<3: return None
    pts=sorted(pts,key=lambda x:x[0])
    base=min(l for _,l in pts); f=fp(dev.get(mint,0)); t0=pts[0][0]
    series=[((bt-t0),((l-base+30e9)**2/K)/f) for bt,l in pts]
    entry=None
    for t,r in series:
        if t<=10 and r>=1.05: entry=(t,r); break
    if not entry: return None
    et,er=entry
    return er,[(t-et,r) for t,r in series if t>=et]

def sim_cap(fwd,er,trail,cap,ride=1.15):
    rem=0.70;real=0.0;peak=er;armed=False
    for t,r in fwd:
        if t>cap: real+=rem*(r/er-1);rem=0;break
        if r>peak:peak=r
        if r>=ride*er:armed=True
        if armed and r<=trail*peak: real+=rem*(r/er-1);rem=0;break
    if rem>0: real+=rem*((fwd[-1][1] if fwd else er)/er-1)
    return real

def sim_cond(fwd,er,trail,dec=40,newhigh=0.97,ride=1.15):
    # run to dec seconds; at dec: if still near its high -> trail onward, else cut at dec price
    rem=0.70;real=0.0;peak=er;armed=False;r_dec=er;p_dec=er
    # phase 1: up to dec, also honor trail if already armed+faded
    i=0
    for t,r in fwd:
        if t>dec:
            break
        if r>peak:peak=r
        if r>=ride*er:armed=True
        if armed and r<=trail*peak: real+=rem*(r/er-1);rem=0;return real
        r_dec=r;p_dec=peak;i+=1
    if rem<=0: return real
    # decision at dec
    if r_dec>=newhigh*p_dec:  # still at/near high -> keep trailing, no cap
        peak=p_dec
        for t,r in fwd:
            if t<dec: continue
            if r>peak:peak=r
            if r<=trail*peak: real+=rem*(r/er-1);rem=0;break
        if rem>0: real+=rem*((fwd[-1][1] if fwd else er)/er-1)
    else:  # fading -> cut at dec
        real+=rem*(r_dec/er-1)
    return real

print(f"{'mint':11} {'entry':>5} {'A:40scap':>9} {'C:trail10':>10} {'D:cond-trail':>12} {'peak':>6}")
tot={'A':0,'C':0,'D':0};n=0
for mint in mints:
    b=build(mint)
    if not b: print(f"{mint[:11]} (no-entry)"); continue
    er,fwd=b; peak=max(r for _,r in fwd)
    A=sim_cap(fwd,er,0.95,40); C=sim_cap(fwd,er,0.90,1e9); D=sim_cond(fwd,er,0.90,40,0.97)
    tot['A']+=A;tot['C']+=C;tot['D']+=D;n+=1
    flag=" <-cond held" if abs(D-A)>0.01 else ""
    print(f"{mint[:11]} {er:>5.2f} {A:>+9.3f} {C:>+10.3f} {D:>+12.3f} {peak:>6.2f}{flag}")
print(f"\nN={n}  entry demand-confirm ~1.05x, 1 SOL")
print(f"TOTAL:  A(40scap)={tot['A']:+.3f}  C(trail10 always)={tot['C']:+.3f}  D(cond-trail: trail only if at new-high@40s)={tot['D']:+.3f}")
print(f"MEAN:   A={tot['A']/n:+.3f}  C={tot['C']/n:+.3f}  D={tot['D']/n:+.3f}")
