import json, sys, collections, concurrent.futures as cf
sys.path.insert(0,'.'); from rpc import rpc
L=json.load(open("landed.json"))
O={}
for l in open("landing-research/raw/outcomes.jsonl"):
    d=json.loads(l)
    if "attempt" in d: O[d["attempt"]]=d
A={}
for l in open("landing-research/raw/attempts.jsonl"):
    d=json.loads(l)
    if "attempt" in d: A[d["attempt"]]=d
VOTE="Vote111111111111111111111111111111111111111"
def keys(t):
    m=t["transaction"]["message"]; la=t["meta"].get("loadedAddresses") or {}
    return list(m["accountKeys"])+la.get("writable",[])+la.get("readonly",[])
def writable(t):
    m=t["transaction"]["message"]; h=m["header"]; ak=m["accountKeys"]; n=len(ak)
    w=[a for i,a in enumerate(ak) if i < h["numRequiredSignatures"]-h["numReadonlySignedAccounts"] or (h["numRequiredSignatures"]<=i<n-h["numReadonlyUnsignedAccounts"])]
    return set(w+(t["meta"].get("loadedAddresses") or {}).get("writable",[]))
def blk(slot):
    try: return slot, rpc("getBlock",[slot,{"encoding":"json","transactionDetails":"full","maxSupportedTransactionVersion":1,"rewards":False}])
    except Exception as e: return slot,None
trig={x["attempt"]:A[x["attempt"]]["trigger"]["txn"] for x in L}
tslot={}
def gt(a):
    try:
        r=rpc("getTransaction",[trig[a],{"encoding":"json","maxSupportedTransactionVersion":1}])
        return a,(r["slot"] if r else None),(r["meta"]["err"] if r else "notfound")
    except Exception as e: return a,None,"rpcerr"
with cf.ThreadPoolExecutor(4) as ex: T={a:(s,e) for a,s,e in ex.map(gt,trig)}
slots=set()
for x in L:
    s,_=T[x["attempt"]]
    lo=min(x["slot"], s or x["slot"]); 
    for z in range(lo, x["slot"]+1): slots.add(z)
with cf.ThreadPoolExecutor(4) as ex: B=dict(ex.map(blk,sorted(slots)))
rows=[]
for x in sorted(L,key=lambda x:x["attempt"]):
    a=x["attempt"]; pools=set(p for p in x["pools"] if p); ts,terr=T[a]
    seq=[]  # (slot, idx, sig, signer, ok, touches)
    for s in range(min(x["slot"],ts or x["slot"]), x["slot"]+1):
        b=B.get(s)
        if not b: continue
        for i,t in enumerate(b["transactions"]):
            k=keys(t)
            if VOTE in t["transaction"]["message"]["accountKeys"]: continue
            sig=t["transaction"]["signatures"][0]
            if sig==trig[a] or sig==x["sig"] or (writable(t)&pools):
                seq.append((s,i,sig,k[0],t["meta"]["err"] is None))
    me=[q for q in seq if q[2]==x["sig"]]; tr=[q for q in seq if q[2]==trig[a]]
    mepos=(me[0][0],me[0][1]) if me else None; trpos=(tr[0][0],tr[0][1]) if tr else None
    between=[q for q in seq if trpos and mepos and trpos<(q[0],q[1])<mepos and q[2] not in (trig[a],x["sig"]) and q[4]]
    if not trpos: verdict="trigger not found"
    elif terr: verdict="PHANTOM (trigger failed)"
    elif trpos>mepos: verdict="WE LANDED BEFORE TRIGGER"
    elif between: verdict=f"TAKEN: {len(between)} ok tx on our pools between"
    else: verdict="trigger then us, nobody between -> price/route wrong?"
    o=O.get(a,{})
    rows.append(dict(a=a,path=x["path"],ms=round((x["t_seen"]-x["t_sent"])/1e6,1) if x.get("t_seen") else None,
        trig_ok=terr is None, trig_err=str(terr)[:40] if terr else "", trig_pos=trpos, our_pos=mepos,
        between=len(between), takers=[q[3][:8] for q in between][:4], err=o.get("err"), exp=x["expected"], verdict=verdict))
for r in rows: print(json.dumps(r))
json.dump(rows,open("why_lost.json","w"))
print(collections.Counter(r["verdict"].split(":")[0] for r in rows))
