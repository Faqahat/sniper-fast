import requests, json, sys, time
RPC=open('/root/snipe_study50/rpc_url.txt').read().strip()
WALLET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
CREATE="d6904cec5f8b31b4"
U64MAX=18446744073709551615
SPEND={"e1f7501ed5b38488","c2ab1c46684d5b2f","38fc74089edfcd5f"}  # read [8:16]
CAP={"66063d1201daebea","b817ee6167c5d33d","07051dc4f5176550"}    # read [16:24]
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
            time.sleep(0.6)
        except:time.sleep(0.7)
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
    spend=[];capfin=[];cap_unbounded=False
    for disc,raw,ix in pix:
        if disc in SPEND and len(raw)>=16:
            spend.append(int.from_bytes(raw[8:16],'little'))
        elif disc in CAP and len(raw)>=24:
            v=int.from_bytes(raw[16:24],'little')
            if v==U64MAX: cap_unbounded=True
            else: capfin.append(v)
    if spend: return max(spend),'spend'
    if capfin: return max(capfin),'cap'
    if cap_unbounded: return U64MAX,'sentinel'
    return 0,'none'

src=json.load(open('/root/snipe_study50/snipes200.json'))
snipes=src['snipes']
out=[]
for i,sn in enumerate(snipes):
    mint=sn['mint'];buyslot=sn['slot']
    rec=dict(sn); rec.update({'create_found':False,'delta':None,'vanilla':None,
        'wire_dev':None,'wire_src':None,'curve_delta':None,'flags_hex':None,'creator':None})
    sigs=mint_sigs(mint)
    rec['mint_total_sigs']=len(sigs)
    if not sigs: out.append(rec); print(f"{i} {mint[:6]} NOSIGS",file=sys.stderr); continue
    min_slot=min(s['slot'] for s in sigs)
    ctx=None;cre=None
    for s in [x for x in sigs if x['slot']==min_slot]:
        t=get_tx(s['signature'])
        if not t:continue
        pix=pump_ixs(t)
        c=[x for x in pix if x[0]==CREATE]
        if c: ctx=t;cre=c[0];break
    if cre is None:
        out.append(rec); print(f"{i} {mint[:6]} NO-CREATE tot={len(sigs)}",file=sys.stderr); continue
    rec['create_found']=True
    cslot=ctx['slot'];rec['create_slot']=cslot;rec['delta']=buyslot-cslot
    raw=cre[1];off=8
    nl=int.from_bytes(raw[off:off+4],'little');off+=4+nl
    sl=int.from_bytes(raw[off:off+4],'little');off+=4+sl
    ul=int.from_bytes(raw[off:off+4],'little');off+=4+ul
    creator=raw[off:off+32];off+=32
    flags=raw[off:]
    rec['creator']=b58e(creator);rec['flags_hex']=flags.hex()
    rec['vanilla']=(len(flags)>0 and all(b==0 for b in flags))
    pix=pump_ixs(ctx)
    wd,ws=wire_dev_buy(pix)
    rec['wire_dev']=wd; rec['wire_src']=ws
    # curve delta truth
    cre_accts=cre[2].get('accounts',[])
    bc=cre_accts[2] if len(cre_accts)>2 else None
    msg=ctx['transaction']['message'];meta=ctx['meta']
    keys=[a['pubkey'] for a in msg['accountKeys']]
    cd=None
    if bc in keys:
        idx=keys.index(bc);cd=meta['postBalances'][idx]-meta['preBalances'][idx]
    rec['curve_delta']=cd
    out.append(rec)
    wds = 'MAX' if wd==U64MAX else f'{wd/1e9:.3f}'
    print(f"{i} {mint[:6]} d={rec['delta']} wire={wds}({ws}) curve={(cd or 0)/1e9:.3f} van={rec['vanilla']}",file=sys.stderr)

json.dump({"meta":src.get('span'),"records":out},open('/root/snipe_study50/enriched200.json','w'),indent=1)
print("DONE",file=sys.stderr)
