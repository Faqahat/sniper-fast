import os,json,time,struct,urllib.request,urllib.error,datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
RPC="https://rpc-frankfurt.constant-k.com/?api-key="+os.environ["CONSTANTK_TOKEN"]
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
SYS="11111111111111111111111111111111"
B58="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
CREATE_V2="d6904cec5f8b31b4"; CREATE="181ec828051c0777"
GW=["https://pump.mypinata.cloud/ipfs/","https://ipfs.io/ipfs/"]
def b58dec(s):
    n=0
    for c in s: n=n*58+B58.index(c)
    full=n.to_bytes((n.bit_length()+7)//8,"big") if n else b""
    return b"\x00"*(len(s)-len(s.lstrip("1")))+full
def b58enc(bb):
    n=int.from_bytes(bb,"big"); out=""
    while n: n,r=divmod(n,58); out=B58[r]+out
    return "1"*(len(bb)-len(bb.lstrip(b"\x00")))+out
def rpc(m,p,tries=6,to=70):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode()
    for t in range(tries):
        try:
            req=urllib.request.Request(RPC,data=body,headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req,timeout=to) as r: j=json.loads(r.read())
            if "error" in j:
                e=j["error"]
                if isinstance(e,dict) and e.get("code")==-32015: return "__VER__"
                time.sleep(0.3*(t+1)); continue
            return j.get("result")
        except urllib.error.HTTPError as e:
            time.sleep(1.0+0.8*t if getattr(e,"code",0)==429 else 0.4*(t+1))
        except Exception:
            time.sleep(0.4*(t+1))
    return None
def get_block(slot):
    return rpc("getBlock",[slot,{"encoding":"jsonParsed","transactionDetails":"accounts","rewards":False,"maxSupportedTransactionVersion":1}])
def get_tx(sig):
    for v in (0,1,2):
        r=rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":v,"encoding":"jsonParsed"}])
        if r and r!="__VER__": return r
    return None
def parse_create(raw):
    p=8; fields=[]
    for _ in range(3):
        if p+4>len(raw): return None
        ln=struct.unpack_from("<I",raw,p)[0]; p+=4
        if ln>4000 or p+ln>len(raw): return None
        fields.append(raw[p:p+ln].decode("utf-8","replace")); p+=ln
    creator=b58enc(raw[p:p+32]) if p+32<=len(raw) else None
    return fields[0],fields[1],fields[2],creator
def fetch_uri(uri):
    tail=None
    if "/ipfs/" in uri: tail=uri.split("/ipfs/",1)[1]
    elif uri.startswith("ipfs://"): tail=uri[7:]
    urls=[g+tail for g in GW] if tail else [uri]
    for u in urls:
        try:
            req=urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req,timeout=8) as r: return json.loads(r.read())
        except Exception: continue
    return None
def has_emoji(s): return any(ord(c)>0x2600 for c in s)

def scan_block_for_mint(res,mint,creator=None):
    # returns list of dicts for txs touching mint (pump), each: fp, sol, got_tokens, is_create
    out=[]
    if not res or res=="__VER__": return out,None
    found_creator=creator
    for t in res.get("transactions",[]):
        tr=t["transaction"]; ak=tr.get("accountKeys") or []
        pubs=[k["pubkey"] for k in ak]
        if mint not in pubs: continue
        if PUMP not in pubs:  # not a pump interaction (ATA ref etc)
            continue
        fp=ak[0]["pubkey"]
        mint_signer=any(k["pubkey"]==mint and k.get("signer") for k in ak)
        meta=t.get("meta") or {}
        pre=meta.get("preBalances") or []; post=meta.get("postBalances") or []
        sol=(pre[0]-post[0])/1e9 if pre and post else 0.0
        pretb=meta.get("preTokenBalances") or []; posttb=meta.get("postTokenBalances") or []
        def amt(tb):
            for b in tb:
                if b.get("mint")==mint and b.get("owner")==fp:
                    return b["uiTokenAmount"].get("uiAmount") or 0.0
            return 0.0
        got=amt(posttb)-amt(pretb)
        if mint_signer and found_creator is None:
            found_creator=fp
        out.append({"fp":fp,"sol":round(sol,5),"got":got,"is_create":mint_signer,"sig":tr["signatures"][0],"err":meta.get("err") is not None})
    return out,found_creator

def creator_funding(creator,create_sig):
    # paginate capped (2 pages) to oldest; find first inbound SOL transfer source
    pages=0; acc=[]; before=None
    while pages<2:
        p=[creator,{"limit":1000}] if before is None else [creator,{"limit":1000,"before":before}]
        s=rpc("getSignaturesForAddress",p,to=45)
        if not s or s=="__VER__": break
        acc+=s; pages+=1
        if len(s)<1000: break
        before=s[-1]["signature"]
    total=len(acc); capped=(pages>=2 and total>=2000)
    # prior sigs before create
    prior=sum(1 for x in acc if x["signature"]!=create_sig)  # approx: all except create (within fetched)
    # count sigs strictly older than create by blockTime
    cbt=None
    for x in acc:
        if x["signature"]==create_sig: cbt=x.get("blockTime")
    prior_before_create=None
    if cbt is not None:
        prior_before_create=sum(1 for x in acc if (x.get("blockTime") or 0) < cbt)
    funder=None; funder_sig=None
    if acc and not capped:
        oldest=acc[-1]["signature"]
        tx=get_tx(oldest)
        if tx:
            msg=tx["transaction"]["message"]; keys=[k["pubkey"] if isinstance(k,dict) else k for k in msg.get("accountKeys",[])]
            meta=tx.get("meta") or {}; pre=meta.get("preBalances") or []; post=meta.get("postBalances") or []
            try: ci=keys.index(creator)
            except ValueError: ci=-1
            if ci>=0 and ci<len(pre) and post[ci]>pre[ci]:
                # creator received SOL; funder = biggest net payer
                best=None;bestd=0
                for i,k in enumerate(keys):
                    if k==creator: continue
                    d=pre[i]-post[i] if i<len(pre) and i<len(post) else 0
                    if d>bestd: bestd=d; best=k
                funder=best; funder_sig=oldest
    return {"creator_total_sigs_capped":capped,"creator_total_sigs":total,"creator_prior_before_create":prior_before_create,"funder":funder}

def extract(row):
    mint=row["mint"]; slot=row["slot"]
    o={"mint":mint,"label":row["label"],"slot":slot,"dev":row["dev"],"dev_sol":row["dev"]/1e9,"vanilla":row.get("vanilla")}
    try:
        b0=get_block(slot); b1=get_block(slot+1)
        h0,creator=scan_block_for_mint(b0,mint)
        # if create not in slot0, look in slot-1
        if creator is None:
            bm=get_block(slot-1); hm,creator=scan_block_for_mint(bm,mint)
            h0=hm+h0
        h1,creator=scan_block_for_mint(b1,mint,creator)
        o["creator"]=creator
        create_sig=next((h["sig"] for h in h0+h1 if h["is_create"]),None)
        o["create_sig"]=create_sig
        # co-buyers: pump txs, not create, feepayer!=creator, got tokens>0, no err
        def cobuys(hits):
            cb={}
            for h in hits:
                if h["is_create"] or h["err"]: continue
                if creator and h["fp"]==creator: continue
                if h["got"]<=0: continue
                prev=cb.get(h["fp"],0)
                cb[h["fp"]]=prev+max(h["sol"],0)
            return cb
        cb0=cobuys(h0); cb01=cobuys(h0+h1)
        o["n_cobuy_slot0"]=len(cb0)
        o["n_cobuy_slot01"]=len(cb01)
        o["sol_cobuy_slot0"]=round(sum(cb0.values()),4)
        o["sol_cobuy_slot01"]=round(sum(cb01.values()),4)
        o["max_cobuy_slot01"]=round(max(cb01.values()),4) if cb01 else 0.0
        o["whale_slot01"]=(o["max_cobuy_slot01"]>5.0)
        tot=o["dev_sol"]+o["sol_cobuy_slot01"]
        o["dev_share_slot01"]=round(o["dev_sol"]/tot,4) if tot>0 else 1.0
        o["n_cobuy_slot1_only"]=len(set(cb01)-set(cb0))
        o["cobuyers"]=list(cb01.keys())
        # create tx parse
        if create_sig:
            tx=get_tx(create_sig)
            if tx:
                bt=tx.get("blockTime")
                if bt:
                    dt=datetime.datetime.utcfromtimestamp(bt); o["hour_utc"]=dt.hour; o["minute"]=dt.minute; o["sec"]=dt.second
                msg=tx["transaction"]["message"]
                ixs=list(msg.get("instructions",[]))
                for inner in (tx.get("meta",{}).get("innerInstructions") or []): ixs+=inner.get("instructions",[])
                craw=None
                for ix in ixs:
                    if ix.get("programId")!=PUMP or not ix.get("data"): continue
                    try: raw=b58dec(ix["data"])
                    except Exception: continue
                    h=raw[:8].hex()
                    if h==CREATE_V2: craw=raw
                    elif h==CREATE and craw is None: craw=raw
                if craw is None:
                    best=None
                    for ix in ixs:
                        if ix.get("programId")==PUMP and ix.get("data"):
                            try: raw=b58dec(ix["data"])
                            except Exception: continue
                            if best is None or len(raw)>len(best): best=raw
                    craw=best
                o["create_disc"]=craw[:8].hex() if craw else None
                pc=parse_create(craw) if craw else None
                if pc:
                    nm,sym,uri,argc=pc
                    o.update({"name":nm,"symbol":sym,"uri":uri,"arg_creator":argc,
                        "name_len":len(nm),"symbol_len":len(sym),
                        "name_has_space":(" " in nm.strip()),
                        "name_has_emoji":has_emoji(nm) or has_emoji(sym),
                        "symbol_upper":sym.isupper(),"name_lower":nm.islower(),
                        "name_upper":nm.isupper(),"name_title":nm.istitle(),
                        "name_has_digit":any(c.isdigit() for c in nm),
                        "symbol_has_digit":any(c.isdigit() for c in sym),
                        "name_wc":len(nm.split()),"name_eq_symbol":nm.strip().lower()==sym.strip().lower()})
                    host=uri.split("://",1)[-1].split("/",1)[0] if uri else "?"
                    o["uri_host"]=host
                    cid=(uri.split("/")[-1] if uri else "")
                    o["cid_style"]=("bafk" if cid.startswith("bafk") else "bafy" if cid.startswith("bafy") else "Qm" if cid.startswith("Qm") else "json" if cid.endswith(".json") else "other")
                    j=fetch_uri(uri)
                    if isinstance(j,dict):
                        low={str(k).lower():v for k,v in j.items()}
                        def pres(ks):
                            for k in ks:
                                v=low.get(k)
                                if v is not None and str(v).strip() not in ("","null","false","#","https://","http://"): return True
                            return False
                        o["has_image"]=bool(low.get("image"))
                        d=low.get("description"); o["desc_len"]=len(str(d).strip()) if d else 0
                        o["has_twitter"]=pres(["twitter","x","twitter_url","x_url"])
                        o["has_telegram"]=pres(["telegram","telegram_url","tg"])
                        o["has_website"]=pres(["website","web","url","homepage"])
                        o["n_socials"]=sum([o["has_twitter"],o["has_telegram"],o["has_website"]])
                        o["n_meta_fields"]=len(j)
                        o["meta_ok"]=True
                    else: o["meta_ok"]=False
        # creator funding/clustering
        if creator:
            o.update(creator_funding(creator,create_sig or ""))
        o["status"]="ok"
    except Exception as e:
        o["status"]="err:"+str(e)[:140]
    return o

def main():
    rows=json.load(open("/root/sep2/labels.json"))
    outp="/root/sep2/features2.json"
    cache={}
    if os.path.exists(outp):
        try: cache=json.load(open(outp))
        except Exception: pass
    todo=[r for r in rows if cache.get(r["mint"],{}).get("status")!="ok"]
    print("total=%d todo=%d"%(len(rows),len(todo)),flush=True)
    out=dict(cache); done=0
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs={ex.submit(extract,r):r["mint"] for r in todo}
        for f in as_completed(futs):
            r=f.result(); out[r["mint"]]=r; done+=1
            print("  %d/%d %s %s cb0=%s cb01=%s solcb=%s whale=%s dev$=%s host=%s cr=%s fund=%s"%(done,len(todo),r["mint"][:8],r.get("status"),r.get("n_cobuy_slot0"),r.get("n_cobuy_slot01"),r.get("sol_cobuy_slot01"),r.get("whale_slot01"),r.get("dev_share_slot01"),str(r.get("uri_host"))[:16],str(r.get("creator"))[:6],str(r.get("funder"))[:6]),flush=True)
            json.dump(out,open(outp,"w"),indent=0)
    json.dump(out,open(outp,"w"),indent=0)
    from collections import Counter
    print("STATUS",Counter(v.get("status","?")[:6] for v in out.values()),flush=True)


if __name__=="__main__":
    main()
