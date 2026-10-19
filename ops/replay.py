import json,urllib.request,base64,hashlib,struct,os,re,concurrent.futures as cf,time
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
    if m and m.group(1) not in [x[0] for x in mints]: mints.append(m.group(1))

# exit simulation on a price-vs-time series (t_sec from entry, r). 30% derisk at entry (locks entry, 0 pnl).
# remaining 70% rides: trailing stop at trail_frac*peak (armed once r>=ride_mult*entry); hard cut at cap_s; cut_r floor.
def sim(series, entry_r, trail_frac, cap_s, ride_mult=1.15):
    # series: list of (t, r) sorted, t>=0 from entry
    rem=0.70; realized=0.30*0.0  # derisk at entry = 0 gain
    peak=entry_r; armed=False
    for t,r in series:
        if t>cap_s:
            realized+=rem*(r/entry_r-1); rem=0; break
        if r>peak: peak=r
        if r>=ride_mult*entry_r: armed=True
        if armed and r<=trail_frac*peak:
            realized+=rem*(r/entry_r-1); rem=0; break
    if rem>0:  # never triggered -> exit at last point
        lr=series[-1][1] if series else entry_r
        realized+=rem*(lr/entry_r-1)
    return realized

print(f"{'mint':12} {'entry':>5} {'A:40s-cap':>10} {'B:trail5%':>10} {'C:trail10%':>11} {'peak':>6}")
tot={'A':0,'B':0,'C':0};n=0
for mint in mints:
    cv=bc(mint)
    sg=[x["signature"] for x in sigs_all(cv)]
    pts=[]
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for v in ex.map(lambda s: tx_point(s,cv), sg):
            if v and v[0]: pts.append(v)
    if len(pts)<3: print(f"{mint[:12]} (insufficient)"); continue
    pts.sort(key=lambda x:x[0])
    t0=pts[0][0]; f=fp(dev.get(mint,0))
    base=min(l for _,l in pts)  # rent floor = curve when fully dumped
    series=[]
    for bt,lam in pts:
        vsol=lam-base+30e9  # real_sol above rent + 30 virtual
        r=(vsol*vsol/K)/f
        series.append((bt-t0, r))
    # entry: first point within 10s where r>=1.05 (demand confirm), else skip
    entry=None
    for t,r in series:
        if t<=10 and r>=1.05: entry=(t,r); break
    if not entry: 
        print(f"{mint[:12]} no-demand-entry (max r early {max(r for t,r in series if t<=10):.2f})"); continue
    et,er=entry
    fwd=[(t-et,r) for t,r in series if t>=et]
    peak=max(r for t,r in fwd)
    A=sim(fwd,er,0.95,40); B=sim(fwd,er,0.95,100000); C=sim(fwd,er,0.90,100000)
    tot['A']+=A;tot['B']+=B;tot['C']+=C;n+=1
    print(f"{mint[:12]} {er:>5.2f} {A:>+10.3f} {B:>+10.3f} {C:>+11.3f} {peak:>6.2f}")
print(f"\nN={n}  entry at demand-confirm (~1.05x), 1 SOL each")
print(f"TOTAL SOL:  A(40s-cap)={tot['A']:+.3f}   B(trail5%,no-cap)={tot['B']:+.3f}   C(trail10%,no-cap)={tot['C']:+.3f}")
print(f"MEAN/trade: A={tot['A']/n:+.3f}   B={tot['B']/n:+.3f}   C={tot['C']/n:+.3f}")
