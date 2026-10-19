import requests,json,sys,time,concurrent.futures as cf,threading
RPC=open('/root/snipe_study50/rpc_url.txt').read().strip()
WALLET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
CB="ComputeBudget111111111111111111111111111111"
CREATE="d6904cec5f8b31b4"
U64MAX=18446744073709551615
SPEND={"e1f7501ed5b38488","c2ab1c46684d5b2f","38fc74089edfcd5f"}
CAP={"66063d1201daebea","b817ee6167c5d33d","07051dc4f5176550"}
_A="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n=0
    for c in s:n=n*58+_A.index(c)
    full=n.to_bytes((n.bit_length()+7)//8,'big');pad=len(s)-len(s.lstrip('1'));return b'\x00'*pad+full
def b58e(b):
    n=int.from_bytes(b,'big');s=''
    while n>0:n,r=divmod(n,58);s=_A[r]+s
    return '1'*(len(b)-len(b.lstrip(b'\x00')))+s
def rpc(m,p,tries=6):
    for i in range(tries):
        try:
            j=requests.post(RPC,json={"jsonrpc":"2.0","id":1,"method":m,"params":p},timeout=35).json()
            if 'result' in j and j['result'] is not None:return j['result']
            if 'error' in j and (j['error'].get('code')==-32019 or 'rate' in str(j['error']).lower()): time.sleep(1.0); continue
            time.sleep(0.4)
        except: time.sleep(0.6)
    return None
def get_tx(sig):return rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":1,"encoding":"jsonParsed"}])
def mint_sigs(mint,maxpages=16):
    out=[];before=None;pages=0
    while pages<maxpages:
        p=[mint,{"limit":1000}]
        if before:p[1]["before"]=before
        r=rpc("getSignaturesForAddress",p)
        if not r:break
        out.extend(r);pages+=1
        if len(r)<1000:break
        before=r[-1]['signature']
    return out
def all_sigs(addr):
    out=[];before=None
    while True:
        p=[addr,{"limit":1000}]
        if before:p[1]["before"]=before
        r=rpc("getSignaturesForAddress",p)
        if not r:break
        out+=r
        if len(r)<1000:break
        before=r[-1]['signature']
    return out
def pump_ixs(tx):
    msg=tx['transaction']['message'];meta=tx.get('meta') or {}
    allix=list(msg.get('instructions',[]))
    for inr in meta.get('innerInstructions',[]):allix+=inr.get('instructions',[])
    res=[]
    for ix in allix:
        if ix.get('programId')!=PUMP:continue
        d=ix.get('data')
        if not d:continue
        try:raw=b58d(d)
        except:continue
        res.append((raw[:8].hex(),raw,ix))
    return res
def wire_dev_buy(pix):
    spend=[];capfin=[];cu=False
    for disc,raw,ix in pix:
        if disc in SPEND and len(raw)>=16: spend.append(int.from_bytes(raw[8:16],'little'))
        elif disc in CAP and len(raw)>=24:
            v=int.from_bytes(raw[16:24],'little')
            if v==U64MAX: cu=True
            else: capfin.append(v)
    if spend: return max(spend),'spend'
    if capfin: return max(capfin),'cap'
    if cu: return U64MAX,'sentinel'
    return 0,'none'
def wallet_lamport_delta(tx,wallet):
    m=tx['meta']; keys=[k['pubkey'] if isinstance(k,dict) else k for k in tx['transaction']['message']['accountKeys']]
    for i,k in enumerate(keys):
        if k==wallet: return m['postBalances'][i]-m['preBalances'][i]
    return 0
def tok_delta(tx,mint,wallet):
    m=tx['meta']
    pre={b['accountIndex']:int(b['uiTokenAmount']['amount']) for b in m.get('preTokenBalances',[]) if b['mint']==mint and b.get('owner')==wallet}
    post={b['accountIndex']:int(b['uiTokenAmount']['amount']) for b in m.get('postTokenBalances',[]) if b['mint']==mint and b.get('owner')==wallet}
    idxs=set(pre)|set(post)
    return sum(post.get(i,0)-pre.get(i,0) for i in idxs)

snipes=json.load(open('/root/dev_pattern/snipes300.json'))['snipes']
# reuse caches
enr_cache={r['mint']:r for r in json.load(open('/root/snipe_study50/enriched200.json'))['records'] if r.get('create_found')}
rows_cache={r['mint']:r for r in json.load(open('/root/exit_study/rows2.json'))}

lock=threading.Lock(); done=[0]
def work(sn):
    mint=sn['mint']; buyslot=sn['slot']
    rec=dict(sn); rec.update(create_found=False,creator=None,deployer=None,create_slot=None,delta=None,
        wire_dev=None,wire_src=None,vanilla=None,create_cu_price=None,flags_hex=None,
        realized=None,peak_r=None,win=None,n_my_tx=None,sol_in=None,sol_out=None,resid_tok=None,pnl_src=None)
    # ---- create tx resolution ----
    cached_e=enr_cache.get(mint)
    if cached_e and cached_e.get('creator'):
        rec.update(create_found=True,creator=cached_e['creator'],create_slot=cached_e.get('create_slot'),
                   delta=cached_e.get('delta'),wire_dev=cached_e.get('wire_dev'),wire_src=cached_e.get('wire_src'),
                   vanilla=cached_e.get('vanilla'),flags_hex=cached_e.get('flags_hex'))
    msigs=mint_sigs(mint)
    if not rec['create_found'] and msigs:
        min_slot=min(s['slot'] for s in msigs); ctx=cre=None
        for s in [x for x in msigs if x['slot']==min_slot]:
            t=get_tx(s['signature'])
            if not t: continue
            pix=pump_ixs(t); c=[x for x in pix if x[0]==CREATE]
            if c: ctx=t; cre=c[0]; break
        if cre is not None:
            rec['create_found']=True; cslot=ctx['slot']; rec['create_slot']=cslot; rec['delta']=buyslot-cslot
            raw=cre[1]; off=8
            nl=int.from_bytes(raw[off:off+4],'little'); off+=4+nl
            sll=int.from_bytes(raw[off:off+4],'little'); off+=4+sll
            ul=int.from_bytes(raw[off:off+4],'little'); off+=4+ul
            creator=raw[off:off+32]; off+=32; flags=raw[off:]
            rec['creator']=b58e(creator); rec['flags_hex']=flags.hex()
            rec['vanilla']=(len(flags)>0 and all(b==0 for b in flags))
            wd,ws=wire_dev_buy(pump_ixs(ctx)); rec['wire_dev']=wd; rec['wire_src']=ws
            # deployer=fee payer of create tx; create cu price
            keys=[a['pubkey'] for a in ctx['transaction']['message']['accountKeys']]
            rec['deployer']=keys[0]
            for ix in ctx['transaction']['message'].get('instructions',[]):
                if ix.get('programId')==CB:
                    try: rr=b58d(ix.get('data'))
                    except: continue
                    if rr and rr[0]==3: rec['create_cu_price']=int.from_bytes(rr[1:9],'little')
    # fill deployer/create_cu even if creator cached (need create tx) -- resolve once
    if rec['create_found'] and rec['deployer'] is None and msigs:
        min_slot=min(s['slot'] for s in msigs)
        for s in [x for x in msigs if x['slot']==min_slot]:
            t=get_tx(s['signature'])
            if not t: continue
            pix=pump_ixs(t)
            if any(x[0]==CREATE for x in pix):
                keys=[a['pubkey'] for a in t['transaction']['message']['accountKeys']]
                rec['deployer']=keys[0]
                for ix in t['transaction']['message'].get('instructions',[]):
                    if ix.get('programId')==CB:
                        try: rr=b58d(ix.get('data'))
                        except: continue
                        if rr and rr[0]==3: rec['create_cu_price']=int.from_bytes(rr[1:9],'little')
                break
    # ---- PnL ----
    rc=rows_cache.get(mint)
    if rc and rc.get('realized') is not None:
        rec['realized']=rc['realized']; rec['peak_r']=rc.get('peak_r'); rec['sol_in']=rc.get('sol_in')
        rec['sol_out']=rc.get('sol_out'); rec['resid_tok']=rc.get('residual'); rec['pnl_src']='rows2'
        rec['win']=rc['realized']>0
    else:
        # compute net wallet SOL delta across HIS txs on this mint via his ATA
        btx=get_tx(sn['sig']); ata=None
        if btx:
            m=btx['meta']
            idx=[b['accountIndex'] for b in m.get('postTokenBalances',[])+m.get('preTokenBalances',[]) if b['mint']==mint and b.get('owner')==WALLET]
            if idx:
                keys=[k['pubkey'] if isinstance(k,dict) else k for k in btx['transaction']['message']['accountKeys']]
                if idx[0]<len(keys): ata=keys[idx[0]]
        net=0; nin=0; nout=0; tok=0; ntx=0
        asigs=all_sigs(ata) if ata else [{'signature':sn['sig']}]
        for s in asigs:
            if s.get('err'): continue
            t=get_tx(s['signature'])
            if not t: continue
            keys=[k['pubkey'] if isinstance(k,dict) else k for k in t['transaction']['message']['accountKeys']]
            if WALLET not in keys: continue
            d=wallet_lamport_delta(t,WALLET); td=tok_delta(t,mint,WALLET)
            if d==0 and td==0: continue
            net+=d; tok+=td; ntx+=1
            if d<0: nin+=-d
            else: nout+=d
        rec['ata']=ata; rec['realized']=net/1e9; rec['sol_in']=nin/1e9; rec['sol_out']=nout/1e9
        rec['resid_tok']=tok; rec['n_my_tx']=ntx; rec['pnl_src']='computed'; rec['win']=net>0
    with lock:
        done[0]+=1
        if done[0]%20==0: print("done",done[0],flush=True)
    return rec

results=[None]*len(snipes)
with cf.ThreadPoolExecutor(max_workers=14) as ex:
    futs={ex.submit(work,sn):i for i,sn in enumerate(snipes)}
    for f in cf.as_completed(futs):
        results[futs[f]]=f.result()
json.dump(results,open('/root/dev_pattern/his_300.json','w'),indent=1)
cf_cnt=sum(1 for r in results if r['create_found'])
print("DONE n=%d create_found=%d pnl_computed=%d"%(len(results),cf_cnt,sum(1 for r in results if r['pnl_src']=='computed')))
