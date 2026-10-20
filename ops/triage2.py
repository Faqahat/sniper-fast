import json, statistics as st, re, glob
PATHS="/root/sniper-fast/paths.jsonl"
rows=[]; mints=set()
for i,line in enumerate(open(PATHS)):
    try: d=json.loads(line)
    except: continue
    if "mint" not in d or "path" not in d or not d["path"]: continue
    if d["mint"] in mints: continue
    mints.add(d["mint"]); d["_ord"]=i; rows.append(d)
FEE=0.0125; FIXED_LEG=0.000365; TIMECAP_MS=3200.0
def net_floor(path, ride=1.3, trail=0.95, entry=1.0):
    tokens=1.0/entry; cost=1.0; proceeds=0.0; peak=entry; riding=False; last=path[0][1]
    for ms,r in path:
        last=r
        if r>peak: peak=r
        if not riding and r>=ride: riding=True
        if (riding and r<=peak*trail) or ms>=TIMECAP_MS:
            proceeds+=tokens*r; tokens=0.0; break
    if tokens>1e-9: proceeds+=tokens*last
    return (1-FEE)**2*proceeds - cost - FIXED_LEG*2
def is_misread(r): return r.get("peak",1.0)>=19.999 or r["path"][0][1]>=10.0
for r in rows: r["_net"]=net_floor(r["path"])
clean=[r for r in rows if not is_misread(r)]

def summ(sub):
    nets=[r["_net"] for r in sub]; n=len(nets)
    if not n: return "EMPTY"
    return f"n={n:4d} tot={sum(nets):+8.2f} mean={sum(nets)/n:+.3f} med={st.median(nets):+.3f} win={100*sum(1 for x in nets if x>0)/n:4.1f}%"

def devbuck(d):
    if d==0: return 0
    if d<=2: return 1
    if d<=5: return 2
    return 3
def key(r): return (r.get("vanilla",True), devbuck(r.get("dev",0)))

# ---- OUT OF SAMPLE: chronological halves ----
print("=== OUT-OF-SAMPLE: chronological split (does dev>=2 edge hold forward?) ===")
half=len(clean)//2
A=clean[:half]; B=clean[half:]
for name,seg in (("1st half",A),("2nd half",B)):
    d2=[r for r in seg if r.get("dev",0)>=2]
    d0=[r for r in seg if r.get("dev",0)==0]
    print(f" {name}: dev>=2  {summ(d2)}")
    print(f" {name}: dev==0  {summ(d0)}")

# ---- DROP NET-NEGATIVE BUCKETS: trade-count reduction & winner retention ----
print("\n=== PRE-BUY GATE candidates (cut net-negative t=0 buckets) ===")
tot_n=len(clean); tot_win=sum(1 for r in clean if r["_net"]>0); tot_net=sum(r["_net"] for r in clean)
print(f" baseline fire-all: {summ(clean)}  winners={tot_win}")
gates={
 "drop (nonvanilla & dev<=2)": lambda r: not((not r.get('vanilla',True)) and r.get('dev',0)<=2),
 "drop (nonvanilla & dev==0)": lambda r: not((not r.get('vanilla',True)) and r.get('dev',0)==0),
 "keep dev>=2 ONLY": lambda r: r.get('dev',0)>=2,
 "keep (vanilla OR dev>=2)": lambda r: r.get('vanilla',True) or r.get('dev',0)>=2,
}
for lab,fn in gates.items():
    kept=[r for r in clean if fn(r)]
    kw=sum(1 for r in kept if r["_net"]>0)
    print(f" {lab:30s}: kept {len(kept):4d} ({100*len(kept)/tot_n:4.1f}% trades) winner-retain={100*kw/tot_win:5.1f}% net-retain={100*sum(r['_net'] for r in kept)/tot_net:5.1f}%  {summ(kept)}")

# ---- ENRICHMENT JOIN from scope logs (mayhem/holder/fee_bps/cashback/poh) ----
print("\n=== ENRICHMENT flags (join LAUNCH lines by mint) ===")
pat=re.compile(r"LAUNCH slot=(\d+) poh_ms=(\S+) mint=(\w+) dev_buy=(\d+) v2=(\w+) vanilla=(\w+) \(mayhem=(\w+) fee_bps=(\d+) holder=(\w+) cashback=(\w+)\) (\w+)")
enr={}
for f in glob.glob("/root/sniper-fast/*.log"):
    try: txt=open(f,errors="ignore").read()
    except: continue
    for m in pat.finditer(txt):
        slot,poh,mint,devbuy,v2,van,may,fee,hold,cash,dec=m.groups()
        pohv=None
        mm=re.search(r"Some\(([\d.]+)\)",poh)
        if mm: pohv=float(mm.group(1))
        enr[mint]={"mayhem":may=="true","fee_bps":int(fee),"holder":hold=="true","cashback":cash=="true","poh":pohv}
net_by_mint={r["mint"]:r["_net"] for r in clean}
joined=[(enr[m],net_by_mint[m]) for m in enr if m in net_by_mint]
print(f" LAUNCH mints parsed={len(enr)}  joined to clean paths={len(joined)}")
if joined:
    for flag in ("mayhem","holder","cashback"):
        for val in (True,False):
            sub=[n for e,n in joined if e[flag]==val]
            if sub: print(f"   {flag}={val}: n={len(sub):3d} mean={sum(sub)/len(sub):+.3f} win={100*sum(1 for x in sub if x>0)/len(sub):4.1f}%")
    # poh timing
    withpoh=[(e["poh"],n) for e,n in joined if e["poh"] is not None]
    if withpoh:
        med=st.median([p for p,_ in withpoh])
        lo=[n for p,n in withpoh if p<med]; hi=[n for p,n in withpoh if p>=med]
        print(f"   poh<med({med:.0f}ms): n={len(lo)} mean={sum(lo)/len(lo):+.3f} | poh>=med: n={len(hi)} mean={sum(hi)/len(hi):+.3f}")
