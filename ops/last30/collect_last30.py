import rpc, json, sys
W=rpc.WALLET
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

def tbals(m,mint):
    pre={b["accountIndex"]:int(b["uiTokenAmount"]["amount"]) for b in m.get("preTokenBalances",[]) if b["mint"]==mint}
    post={b["accountIndex"]:int(b["uiTokenAmount"]["amount"]) for b in m.get("postTokenBalances",[]) if b["mint"]==mint}
    owners={}
    for b in m.get("preTokenBalances",[])+m.get("postTokenBalances",[]):
        if b["mint"]==mint: owners[b["accountIndex"]]=b.get("owner")
    return pre,post,owners

def analyze(tx):
    m=tx["meta"]; msg=tx["transaction"]["message"]
    keys=[k["pubkey"] if isinstance(k,dict) else k for k in msg["accountKeys"]]
    la=m.get("loadedAddresses") or {}
    allk=keys+la.get("writable",[])+la.get("readonly",[])
    pump_present = PUMP in allk
    mints=set(b["mint"] for b in m.get("preTokenBalances",[])+m.get("postTokenBalances",[]))
    out=[]
    for mint in mints:
        pre,post,owners=tbals(m,mint)
        wal_idx=[i for i,o in owners.items() if o==W]
        if not wal_idx: continue
        wtok=sum(post.get(i,0)-pre.get(i,0) for i in wal_idx)
        out.append((mint,wtok))
    wsol=m["postBalances"][0]-m["preBalances"][0]
    return pump_present,out,wsol

def all_sigs_recent(addr,cap=4000):
    out=[];before=None
    while len(out)<cap:
        page=rpc.getsigs(addr,before=before,limit=1000)
        if not page: break
        out+=page
        if len(page)<1000: break
        before=page[-1]["signature"]
    return out

print("listing wallet sigs...",file=sys.stderr)
sigs=all_sigs_recent(W,4000)
succ=[s for s in sigs if s.get("err") is None]
print("total %d succ %d"%(len(sigs),len(succ)),file=sys.stderr)

positions=[]
seen=set()
scanned=0
for s in succ:
    if len(positions)>=30: break
    tx=rpc.gettx(s["signature"])
    scanned+=1
    if not tx: continue
    try:
        pp,out,wsol=analyze(tx)
    except Exception as e:
        continue
    if not pp: continue
    buys=[(mint,wtok) for mint,wtok in out if wtok>0]
    if not buys: continue
    mint,wtok=max(buys,key=lambda x:x[1])
    if mint in seen: continue
    seen.add(mint)
    slot=tx["slot"]
    positions.append({"sig":s["signature"],"slot":slot,"blockTime":tx.get("blockTime"),
                      "mint":mint,"buy_tok":wtok,"buy_sol_delta":wsol})
    print("  pos %d slot %d mint %s tok %d sol %.3f"%(len(positions),slot,mint[:8],wtok,wsol/1e9),file=sys.stderr)

json.dump({"positions":positions,"scanned":scanned,"n_sigs":len(sigs),"n_succ":len(succ)},
          open("/root/last30/positions.json","w"),indent=1)
print("wrote %d positions, scanned %d"%(len(positions),scanned),file=sys.stderr)
