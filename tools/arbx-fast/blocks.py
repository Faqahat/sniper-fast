import json, sys, collections, statistics as st, concurrent.futures as cf
sys.path.insert(0,'.'); from rpc import rpc
exec(open("an.py").read().split("txs=json.load")[0])   # b58d
S=json.load(open("/home/moiz/arbed/arbx-fast/data/sender-tip-accounts.json"))
tipsvc={}
for svc,v in S.items():
    for a in (v.get("tip_accounts") or []) if isinstance(v,dict) else []: tipsvc[a]="jito" if svc=="quicknode_lil_jit" else svc
VM=json.load(open("/home/moiz/arbed/arbx-fast/data/validators-meta.json"))["validators"]
VOTE="Vote111111111111111111111111111111111111111"; CB="ComputeBudget111111111111111111111111111111"
L=json.load(open("landed.json"))
def keys(t):
    m=t["transaction"]["message"]; k=list(m["accountKeys"]); la=t["meta"].get("loadedAddresses") or {}
    return k+la.get("writable",[])+la.get("readonly",[])
def writable(t):
    m=t["transaction"]["message"]; h=m["header"]; ak=m["accountKeys"]; n=len(ak)
    w=[a for i,a in enumerate(ak) if i < h["numRequiredSignatures"]-h["numReadonlySignedAccounts"] or (h["numRequiredSignatures"]<=i<n-h["numReadonlyUnsignedAccounts"])]
    return set(w+(t["meta"].get("loadedAddresses") or {}).get("writable",[]))
def info(t):
    k=keys(t); m=t["transaction"]["message"]; price=0; tips=[]
    for ix in m["instructions"]:
        p=k[ix["programIdIndex"]]; d=b58d(ix["data"])
        if p==CB and d[:1]==b'\x03': price=int.from_bytes(d[1:9],'little')
        if p=="11111111111111111111111111111111" and d[:4]==b'\x02\x00\x00\x00':
            to=k[ix["accounts"][1]]
            if to in tipsvc: tips.append((tipsvc[to],int.from_bytes(d[4:12],'little')))
    vote=any(k[ix["programIdIndex"]]==VOTE for ix in m["instructions"])
    nsig=m["header"]["numRequiredSignatures"]; prio=t["meta"]["fee"]-5000*nsig
    return {"sig":t["transaction"]["signatures"][0],"signer":k[0],"price":price,"prio":prio,"tips":tips,"vote":vote,"err":bool(t["meta"]["err"]),"w":writable(t)}
def blk(slot):
    try: return slot, rpc("getBlock",[slot,{"encoding":"json","transactionDetails":"full","maxSupportedTransactionVersion":1,"rewards":False}])
    except Exception: return slot,None
slots=sorted({x["slot"] for x in L}|{x["trig_slot"] for x in L if x.get("trig_slot")})
with cf.ThreadPoolExecutor(4) as ex: B=dict(ex.map(blk,slots))
try: leaders={s:rpc("getSlotLeaders",[s,1])[0] for s in sorted({x["slot"] for x in L})}
except Exception: leaders={}
def spearman(a,b):
    import math
    ra=[sorted(a).index(x) for x in a]; rb=[sorted(b).index(x) for x in b]
    n=len(a); ma=sum(ra)/n; mb=sum(rb)/n
    c=sum((x-ma)*(y-mb) for x,y in zip(ra,rb)); va=sum((x-ma)**2 for x in ra); vb=sum((y-mb)**2 for y in rb)
    return c/math.sqrt(va*vb) if va and vb else 0
rows=[]
for x in L:
    b=B.get(x["slot"])
    if not b: continue
    T=[info(t) for t in b["transactions"]]
    nv=[(i,t) for i,t in enumerate(T) if not t["vote"]]
    me=[(i,t) for i,t in nv if t["sig"]==x["sig"]]
    if not me: continue
    mi,mt=me[0]
    pos=[j for j,(i,t) in enumerate(nv) if i==mi][0]
    prices=[t["price"] for _,t in nv]
    pct_price=sum(1 for p in prices if p<=mt["price"])/len(prices)
    pools=set(p for p in x["pools"] if p)
    ahead=[t for i,t in nv if i<mi and (t["w"]&pools) and not t["err"]]
    rho=spearman([i for i,_ in nv],[t["price"] for _,t in nv])
    ld=leaders.get(x["slot"]); lm=VM.get(ld) or {}
    rows.append({"a":x["attempt"],"path":x["path"],"slot_off":x["slot"]-(x.get("trig_slot") or x["slot"]),"pos":pos,"n":len(nv),"pos_pct":pos/len(nv),
                 "my_price":mt["price"],"my_prio":mt["prio"],"price_pct":pct_price,"median_price":st.median(prices),"rho":rho,
                 "ahead":len(ahead),"ahead_prio_med":st.median([t["prio"] for t in ahead]) if ahead else None,
                 "ahead_tipped":sum(1 for t in ahead if t["tips"]),"leader_kind":"bam" if lm.get("bam") else ("jito" if lm.get("jito") else "plain"),
                 "send_to_land_ms":(x["t_seen"]-x["t_sent"])/1e6 if x.get("t_sent") else None})
json.dump(rows,open("blocks_rows.json","w"))
print(f"{'att':>4} {'path':9} {'slot+':>5} {'pos/n':>9} {'pos%':>5} {'our CUprice':>11} {'our prio':>8} {'price pctile':>12} {'blk median price':>16} {'rho(idx,price)':>14} {'ahead on pools':>14} {'ahead prio p50':>14} {'leader':>6} {'send->land':>10}")
for r in rows:
    print(f"{r['a']:>4} {r['path']:9} {r['slot_off']:>5} {str(r['pos'])+'/'+str(r['n']):>9} {r['pos_pct']*100:5.0f} {r['my_price']:>11,} {r['my_prio']:>8,} {r['price_pct']*100:11.0f}% {r['median_price']:>16,.0f} {r['rho']:>14.2f} {r['ahead']:>14} {str(r['ahead_prio_med']):>14} {r['leader_kind']:>6} {r['send_to_land_ms'] or 0:>9.0f}ms")
