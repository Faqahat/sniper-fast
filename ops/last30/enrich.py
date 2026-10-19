import rpc, json, sys, concurrent.futures as cf, threading
W=rpc.WALLET
FCDY="FCdY3UTqSrbKab7ba3V6LDVSwYue2GD1xyq8tPY6Yr3o"
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
CB="ComputeBudget111111111111111111111111111111"
CREATE=bytes([0xd6,0x90,0x4c,0xec,0x5f,0x8b,0x31,0xb4])
BUYS={"e1f7501ed5b38488":"v3","c2ab1c46684d5b2f":"v2q","38fc74089edfcd5f":"exactsol","66063d1201daebea":"buy","b817ee6167c5d33d":"v2","07051dc4f5176550":"v3old"}
JITO={"96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5","HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe","Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY","ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49","DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh","ADuUkR4vqLUMWXxW9gh6D6L8pGAyzx4q8tY7s9Z6bK7","DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL","3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT"}
_A="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n=0
    for c in s: n=n*58+_A.index(c)
    o=bytearray()
    while n>0: o.append(n&0xff); n>>=8
    o.reverse(); return bytes(len(s)-len(s.lstrip('1')))+bytes(o)

def parse_trade(tx,mint):
    m=tx["meta"]
    keys=[k["pubkey"] if isinstance(k,dict) else k for k in tx["transaction"]["message"]["accountKeys"]]
    pre=m["preBalances"]; post=m["postBalances"]
    preT={b["accountIndex"]:int(b["uiTokenAmount"]["amount"]) for b in m.get("preTokenBalances",[]) if b["mint"]==mint}
    postT={b["accountIndex"]:int(b["uiTokenAmount"]["amount"]) for b in m.get("postTokenBalances",[]) if b["mint"]==mint}
    owners={}
    for b in m.get("preTokenBalances",[])+m.get("postTokenBalances",[]):
        if b["mint"]==mint: owners[b["accountIndex"]]=b.get("owner")
    wal_idx=[i for i,o in owners.items() if o==W]
    curve_idx=[i for i,o in owners.items() if o and o!=W]
    def td(i): return postT.get(i,0)-preT.get(i,0)
    wtok=sum(td(i) for i in wal_idx)
    curve_owner=owners[curve_idx[0]] if curve_idx else None
    csol=0; ctok=0
    if curve_owner:
        for i,k in enumerate(keys):
            if k==curve_owner: csol=post[i]-pre[i]; break
        ci=[i for i in curve_idx]
        ctok=sum(td(i) for i in ci)
    wsol=post[0]-pre[0]
    ataidx=[b["accountIndex"] for b in m.get("postTokenBalances",[])+m.get("preTokenBalances",[]) if b["mint"]==mint and b.get("owner")==W]
    ata=keys[ataidx[0]] if ataidx else None
    resid=sum(postT.get(i,0) for i in wal_idx)
    return dict(slot=tx["slot"],bt=tx.get("blockTime"),wtok=wtok,csol=csol,ctok=ctok,wsol=wsol,curve=curve_owner,ata=ata,resid=resid)

def all_sigs(addr):
    out=[];before=None
    while True:
        page=rpc.getsigs(addr,before=before,limit=1000)
        if not page: break
        out+=page
        if len(page)<1000: break
        before=page[-1]["signature"]
    return out

def find_create_slot(mint,buy_slot=None,hi=None):
    before=None; last=None; pages=0; total=0; win=[]
    while pages<40:
        o={"limit":1000}
        if before: o["before"]=before
        page=rpc.call("getSignaturesForAddress",[mint,o])
        if not page: break
        total+=len(page); last=page[-1]; pages+=1
        if buy_slot is not None:
            for s in page:
                sl=s.get("slot")
                if sl is not None and buy_slot<=sl<=hi: win.append(s)
        if len(page)<1000: break
        before=page[-1]["signature"]
    return (last["slot"] if last else None), total, win

def parse_block_buys(slot,mint):
    b=rpc.call("getBlock",[slot,{"encoding":"json","transactionDetails":"full","maxSupportedTransactionVersion":1,"rewards":False}])
    if not b: return None
    txs=b["transactions"]
    rows=[]  # in block order
    for idx,tx in enumerate(txs):
        msg=tx["transaction"]["message"]; keys=msg["accountKeys"]
        la=tx.get("meta",{}).get("loadedAddresses",{}) or {}
        allk=keys+la.get("writable",[])+la.get("readonly",[])
        if PUMP not in allk or mint not in allk: continue
        meta=tx["meta"]
        signer=keys[0]
        cup=0;cul=0;iscre=False;isbuy=None;vanilla=None
        allins=list(msg["instructions"])
        for inner in meta.get("innerInstructions",[]):
            allins+=inner.get("instructions",[])
        for ins in allins:
            prog=allk[ins["programIdIndex"]]
            if prog!=PUMP and prog!=CB: continue
            try: d=b58d(ins["data"])
            except: continue
            if prog==CB and d:
                if d[0]==3 and len(d)>=9: cup=int.from_bytes(d[1:9],"little")
                elif d[0]==2 and len(d)>=5: cul=int.from_bytes(d[1:5],"little")
            if prog==PUMP:
                if d[:8]==CREATE:
                    iscre=True
                    vanilla = (len(d)>=11) and all(b==0 for b in d[-11:])
                elif d[:8].hex() in BUYS: isbuy=BUYS[d[:8].hex()]
        if not iscre and not isbuy: continue
        # curve sol/tok delta
        preT={x["accountIndex"]:int(x["uiTokenAmount"]["amount"]) for x in meta.get("preTokenBalances",[]) if x["mint"]==mint}
        postT={x["accountIndex"]:int(x["uiTokenAmount"]["amount"]) for x in meta.get("postTokenBalances",[]) if x["mint"]==mint}
        owners={}
        for x in meta.get("preTokenBalances",[])+meta.get("postTokenBalances",[]):
            if x["mint"]==mint: owners[x["accountIndex"]]=x.get("owner")
        curve_idx=[i for i,o in owners.items() if o and o!=signer and o not in (None,)]
        # curve = token acct NOT owned by the signer (the bonding curve PDA)
        buyer_idx=[i for i,o in owners.items() if o==signer]
        tok_in=sum(postT.get(i,0)-preT.get(i,0) for i in buyer_idx)
        # curve sol delta
        csol=0;ctok=0
        # curve owner = owner appearing that's not signer; its lamport delta
        cowners=set(o for i,o in owners.items() if o and o!=signer)
        for i,k in enumerate(allk):
            if k in cowners:
                csol+=meta["postBalances"][i]-meta["preBalances"][i]
        ctok=sum(postT.get(i,0)-preT.get(i,0) for i in curve_idx)
        tip=sum(max(0,meta["postBalances"][i]-meta["preBalances"][i]) for i,k in enumerate(allk) if k in JITO)
        fee=meta["fee"]
        err=meta["err"] is None
        rows.append(dict(idx=idx,signer=signer,iscre=iscre,isbuy=isbuy,vanilla=vanilla,cu_price=cup,cu_limit=cul,
                         prio_lam=cup*cul//1000000,jito_tip=tip,fee=fee,ok=err,
                         tok_in=tok_in,csol=csol,ctok=ctok))
    return rows

lock=threading.Lock(); done=[0]
def work(pos):
    mint=pos["mint"]; r={"mint":mint,"buy_sig":pos["sig"],"buy_slot":pos["slot"],"bt":pos["blockTime"]}
    try:
        btx=rpc.gettx(pos["sig"])
        bt=parse_trade(btx,mint)
        ata=bt["ata"]; curve=bt["curve"]
        r["ata"]=ata; r["curve"]=curve
        # entry price from curve delta on his buy
        entry_sol=abs(bt["csol"]); entry_tok=abs(bt["wtok"])
        r["buy_sol_in"]=entry_sol; r["buy_tok"]=entry_tok
        r["entry_px"]=entry_sol/entry_tok if entry_tok else None
        # all his trades
        sigs=all_sigs(ata)
        trades=[]
        for s in sigs:
            if s.get("err"): continue
            tx=rpc.gettx(s["signature"])
            if tx is None: continue
            tr=parse_trade(tx,mint); tr["sig"]=s["signature"]
            trades.append(tr)
        trades.sort(key=lambda t:t["slot"])
        r["n_trade_fetch"]=len(trades)
        pnl=sum(t["wsol"] for t in trades)/1e9
        sells=[t for t in trades if t["wtok"]<0]
        buys=[t for t in trades if t["wtok"]>0]
        resid=trades[-1]["resid"] if trades else None
        r["pnl_sol"]=pnl; r["n_trades"]=len(trades); r["n_buys"]=len(buys); r["n_sells"]=len(sells)
        r["resid_tok"]=resid
        r["last_sell_slot"]=sells[-1]["slot"] if sells else None
        r["first_sell_slot"]=sells[0]["slot"] if sells else None
        r["win"]= pnl>0
        # create slot forensics (+ collect post-entry window sigs for peak)
        hiwin=min((r.get("last_sell_slot") or pos["slot"]+200), pos["slot"]+400)
        cslot,nsig,winsigs=find_create_slot(mint,pos["slot"],hiwin)
        r["create_slot"]=cslot; r["n_mint_sigs"]=nsig; r["slot_delta"]=(pos["slot"]-cslot) if cslot else None
        blk_rows=None
        # parse create block
        if cslot:
            blk_rows=parse_block_buys(cslot,mint)
        # his buy may be in a different slot; parse his buy slot block too for same-slot ranking
        buy_rows=parse_block_buys(pos["slot"],mint) if pos["slot"]!=cslot else blk_rows
        r["create_features"]=summarize_create(blk_rows,cslot,mint) if blk_rows else None
        r["fill"]=summarize_fill(buy_rows,pos["slot"]) if buy_rows else None
        # peak (isolated so failure doesn't lose PnL)
        try:
            r["peak_mult"],r["npk"]=peak_from_sigs(winsigs,pos["slot"],r["entry_px"],curve)
        except Exception as pe:
            r["peak_mult"]=None; r["peak_err"]=repr(pe)
    except Exception as e:
        import traceback
        r["error"]=repr(e)
        r["tb"]=traceback.format_exc()[-400:]
    with lock:
        done[0]+=1
        print("done",done[0],mint[:8],r.get("pnl_sol"),"err" if r.get("error") else "",file=sys.stderr)
    return r

def summarize_create(rows,cslot,mint):
    # dev = create tx (iscre). dev_buy = its bonding-curve sol inflow (tok bought bundled in create)
    cre=[x for x in rows if x["iscre"]]
    buys=[x for x in rows if x["isbuy"] and x["ok"]]
    out={}
    if cre:
        c=cre[0]
        out["create_cu_price"]=c["cu_price"]
        out["create_jito_tip"]=c["jito_tip"]
        # dev buy = sol into curve during create tx = csol positive
        out["dev_buy_sol"]=max(0,c["csol"])/1e9
        out["create_idx"]=c["idx"]
        out["vanilla"]=c.get("vanilla")
    else:
        out["create_cu_price"]=None; out["dev_buy_sol"]=None; out["create_idx"]=None; out["create_jito_tip"]=None
    # co-snipers in create slot = successful external buys (signer != dev creator)
    dev_signer=cre[0]["signer"] if cre else None
    ext=[x for x in buys if x["signer"]!=dev_signer]
    out["cosnipers_create_slot"]=len(set(x["signer"] for x in ext))
    out["n_buys_create_slot"]=len(buys)
    # bundled flag: jito tip on create, or there exist 0-fee external buys adjacent
    out["bundled"]= (cre and cre[0]["jito_tip"]>0) or any(x["jito_tip"]>0 for x in buys)
    return out

def summarize_fill(rows,buy_slot):
    # rank among same-slot successful external buys by block idx
    buys=[x for x in rows if x["isbuy"] and x["ok"]]
    buys.sort(key=lambda x:x["idx"])
    # his rows: signer==W or signer==FCDY (his program is signer? no, signer is feepayer=W). match W
    his=[i for i,x in enumerate(buys) if x["signer"]==W]
    out={"n_sameslot_buys":len(buys)}
    if not his:
        out["his_rank"]=None; out["fill_ratio"]=None; out["floor_px"]=None; out["his_px"]=None
        return out
    hi=his[0]
    out["his_rank"]=hi+1  # 1-indexed among external buyers ordered by block idx
    # his block idx
    out["his_blkidx"]=buys[hi]["idx"]
    # floor price = first external buy's execution px
    def px(x):
        if x["tok_in"]>0 and x["csol"]!=0: return abs(x["csol"])/abs(x["tok_in"])
        return None
    floor=None
    for x in buys:
        p=px(x)
        if p: floor=p; break
    hp=px(buys[hi])
    out["floor_px"]=floor; out["his_px"]=hp
    out["fill_ratio"]= (hp/floor) if (hp and floor) else None
    return out

def price_from_tx(tx,curve):
    # price of any trade = |curve lamport delta| / |curve token-account delta|
    m=tx["meta"]
    keys=[k["pubkey"] if isinstance(k,dict) else k for k in tx["transaction"]["message"]["accountKeys"]]
    la=m.get("loadedAddresses") or {}
    allk=keys+[ (k if isinstance(k,str) else k) for k in la.get("writable",[])+la.get("readonly",[])]
    csol=0
    for i,k in enumerate(allk):
        if k==curve and i<len(m["postBalances"]): csol+=m["postBalances"][i]-m["preBalances"][i]
    preT={b["accountIndex"]:int(b["uiTokenAmount"]["amount"]) for b in m.get("preTokenBalances",[]) if b.get("owner")==curve}
    postT={b["accountIndex"]:int(b["uiTokenAmount"]["amount"]) for b in m.get("postTokenBalances",[]) if b.get("owner")==curve}
    idxs=set(preT)|set(postT)
    ctok=sum(postT.get(i,0)-preT.get(i,0) for i in idxs)
    if csol==0 or ctok==0: return None
    return abs(csol)/abs(ctok)

def peak_from_sigs(winsigs,buy_slot,entry_px,curve):
    if not entry_px: return None,0
    inwin=sorted(winsigs,key=lambda s:s.get("slot") or 0)
    if len(inwin)>70:
        step=len(inwin)/70.0
        inwin=[inwin[int(i*step)] for i in range(70)]
    peak=1.0; n=0
    for s in inwin:
        tx=rpc.gettx(s["signature"])
        if not tx: continue
        p=price_from_tx(tx,curve)
        if not p: continue
        rr=p/entry_px
        if rr>peak: peak=rr
        n+=1
    return round(peak,3),n

if __name__=="__main__":
    positions=json.load(open("/root/last30/positions.json"))["positions"]
    results=[None]*len(positions)
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        futs={ex.submit(work,p):i for i,p in enumerate(positions)}
        for f in cf.as_completed(futs):
            results[futs[f]]=f.result()
    json.dump(results,open("/root/last30/enriched.json","w"),indent=1)
    errs=[r for r in results if r.get("error")]
    print("TOTAL",len(results),"errors",len(errs),file=sys.stderr)
    for e in errs[:8]: print("ERR",e["mint"][:8],e.get("error"),e.get("tb"),file=sys.stderr)
