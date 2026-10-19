import requests, json, sys, time
RPC=open('/root/snipe_study50/rpc_url.txt').read().strip()
WALLET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
EXACT="e1f7501ed5b38488"; CLASSIC="66063d1201daebea"; CREATE="d6904cec5f8b31b4"
_A="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n=0
    for c in s:n=n*58+_A.index(c)
    full=n.to_bytes((n.bit_length()+7)//8,'big');pad=len(s)-len(s.lstrip('1'));return b'\x00'*pad+full
def b58e(b):
    n=int.from_bytes(b,'big');s=''
    while n>0:n,r=divmod(n,58);s=_A[r]+s
    return '1'*(len(b)-len(b.lstrip(b'\x00')))+s
def rpc(m,p,tries=5):
    for i in range(tries):
        try:
            j=requests.post(RPC,json={"jsonrpc":"2.0","id":1,"method":m,"params":p},timeout=35).json()
            if 'result' in j:return j['result']
            time.sleep(0.8)
        except:time.sleep(0.8)
    return None
def get_tx(sig):return rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
def mint_sigs(mint):
    out=[];before=None;pages=0
    while pages<3:
        p=[mint,{"limit":1000}]
        if before:p[1]["before"]=before
        r=rpc("getSignaturesForAddress",p)
        if not r:break
        out.extend(r);pages+=1
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

d=json.load(open('/root/snipe_study50/snipes.json'))
snipes=d['snipes']
out=[]
for i,sn in enumerate(snipes):
    mint=sn['mint'];buyslot=sn['slot']
    rec=dict(sn); rec['create_found']=False; rec['delta']=None
    rec['dev_buy_lamports']=None; rec['creator']=None; rec['vanilla']=None
    rec['flags_hex']=None; rec['cosnipers_createslot']=None; rec['cosnipers_buyslot']=None
    sigs=mint_sigs(mint)
    rec['mint_total_sigs']=len(sigs)
    if not sigs:
        out.append(rec); print(f"{i} {mint[:6]} NO SIGS",file=sys.stderr); continue
    sigs_sorted=sorted(sigs,key=lambda x:(x['slot'], x.get('blockTime') or 0))
    oldest=sigs_sorted[0]
    ctx=get_tx(oldest['signature'])
    if ctx:
        pix=pump_ixs(ctx)
        cre=[x for x in pix if x[0]==CREATE]
        if cre:
            rec['create_found']=True
            cslot=ctx['slot']; rec['create_slot']=cslot; rec['delta']=buyslot-cslot
            raw=cre[0][1]
            off=8
            nl=int.from_bytes(raw[off:off+4],'little');off+=4+nl
            sl=int.from_bytes(raw[off:off+4],'little');off+=4+sl
            ul=int.from_bytes(raw[off:off+4],'little');off+=4+ul
            creator=raw[off:off+32];off+=32
            flags=raw[off:]
            rec['creator']=b58e(creator)
            rec['flags_hex']=flags.hex()
            rec['vanilla']=(len(flags)>0 and all(b==0 for b in flags))
            # dev buy: bonding curve = create instruction account[2]
            cre_accts=cre[0][2].get('accounts',[])
            bc=cre_accts[2] if len(cre_accts)>2 else None
            has_buy=any(x[0] in (EXACT,CLASSIC) for x in pix)
            msg=ctx['transaction']['message'];meta=ctx['meta']
            keys=[a['pubkey'] for a in msg['accountKeys']]
            dev_buy=0
            if has_buy and bc in keys:
                idx=keys.index(bc); dev_buy=meta['postBalances'][idx]-meta['preBalances'][idx]
            rec['dev_buy_lamports']=dev_buy
        else:
            rec['oldest_is_create']=False
    # co-snipers: distinct buyers (pump buy, buyer!=wallet) in create_slot and buy_slot
    def count_buyers(slot):
        buyers=set()
        slist=[s for s in sigs if s['slot']==slot and s.get('err') is None]
        for s in slist[:30]:
            t=get_tx(s['signature'])
            if not t:continue
            for disc,raw,ix in pump_ixs(t):
                if disc==EXACT:
                    ac=ix.get('accounts',[])
                    if len(ac)>=9:
                        b=ac[8]
                        if b!=WALLET:buyers.add(b)
                elif disc==CLASSIC:
                    # classic buy: buyer is a signer; use fee payer of tx
                    fp=t['transaction']['message']['accountKeys'][0]['pubkey']
                    if fp!=WALLET:buyers.add(fp)
        return len(buyers)
    if rec.get('create_slot') is not None:
        rec['cosnipers_createslot']=count_buyers(rec['create_slot'])
    rec['cosnipers_buyslot']=count_buyers(buyslot)
    out.append(rec)
    print(f"{i} {mint[:6]} d={rec['delta']} dev={ (rec['dev_buy_lamports'] or 0)/1e9:.3f} van={rec['vanilla']} co_c={rec['cosnipers_createslot']} co_b={rec['cosnipers_buyslot']} tot={rec['mint_total_sigs']}",file=sys.stderr)

json.dump({"meta":{k:d[k] for k in ('n_sigs','n_succ','n_err','span','scanned')},"records":out},
          open('/root/snipe_study50/enriched.json','w'),indent=1)
print("wrote enriched.json",file=sys.stderr)
