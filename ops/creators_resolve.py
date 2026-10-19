import os, json, time, sys, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
RPC="https://rpc-frankfurt.constant-k.com/?api-key="+os.environ["CONSTANTK_TOKEN"]
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
LIMIT_POP=int(os.environ.get("LIMIT_POP","3500"))

def rpc(m,p,tries=8):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode()
    last=None
    for t in range(tries):
        try:
            req=urllib.request.Request(RPC,data=body,headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req,timeout=45) as r: j=json.loads(r.read())
            if "error" in j:
                last=j["error"]
                if isinstance(last,dict) and last.get("code")==-32015: return ("__VERR__",)
                time.sleep(0.3*(t+1)); continue
            return j.get("result")
        except urllib.error.HTTPError as e:
            last=e; time.sleep(1.0+0.8*t if getattr(e,"code",0)==429 else 0.4*(t+1))
        except Exception as e:
            last=e; time.sleep(0.4*(t+1))
    return None

def get_tx(sig):
    for v in (0,1,2):
        res=rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":v,"encoding":"jsonParsed"}])
        if isinstance(res,tuple): continue
        return res
    return None

def creator_from_tx(tx):
    if not tx: return None
    msg=tx["transaction"]["message"]
    keys=[k["pubkey"] if isinstance(k,dict) else k for k in msg.get("accountKeys",[])]
    return keys[0] if keys else None

def resolve_pick(item):
    mint,v=item
    cs=v.get("create_sig")
    if not cs: return (mint,None)
    return (mint, creator_from_tx(get_tx(cs)))

def resolve_mint(mint):
    # find oldest sig (create) then fee payer
    r=rpc("getSignaturesForAddress",[mint,{"limit":1000}])
    if not r: return (mint,None)
    if len(r)>=1000:
        # token too active; page to oldest (cap pages to avoid blowup)
        before=r[-1]["signature"]; pages=1
        while pages<6:
            r2=rpc("getSignaturesForAddress",[mint,{"limit":1000,"before":before}])
            if not r2: break
            before=r2[-1]["signature"]; pages+=1
            if len(r2)<1000:
                r=r2; break
        else:
            return (mint,None)  # gave up
    oldest=r[-1]["signature"]
    return (mint, creator_from_tx(get_tx(oldest)))

def main():
    # ---- picks (4yFAz bought tokens) ----
    exp=json.load(open("/root/expanded_raw.json"))
    pick_items=[(m,v) for m,v in exp.items() if v.get("status")=="ok" and v.get("create_sig")]
    print(f"picks to resolve: {len(pick_items)}",file=sys.stderr)
    picks={}
    with ThreadPoolExecutor(max_workers=16) as ex:
        futs={ex.submit(resolve_pick,it):it for it in pick_items}
        done=0
        for f in as_completed(futs):
            m,c=f.result(); picks[m]=c; done+=1
            if done%100==0: print(f"  picks {done}/{len(pick_items)}",file=sys.stderr)
    pick_mints=set(picks)

    # ---- population mints from broad launch logs ----
    pop_mints=[]
    seen=set()
    for path in ("/root/arbx-fast/paths_broad.jsonl","/root/arbx-fast/paths.jsonl","/root/gs_clean/paths.jsonl"):
        try:
            for line in open(path):
                line=line.strip()
                if not line: continue
                try: o=json.loads(line)
                except Exception: continue
                if not isinstance(o,dict): continue
                mt=o.get("mint")
                if mt and mt not in seen and mt not in pick_mints:
                    seen.add(mt); pop_mints.append(mt)
        except FileNotFoundError: pass
        if len(pop_mints)>=LIMIT_POP: break
    pop_mints=pop_mints[:LIMIT_POP]
    print(f"population mints to resolve: {len(pop_mints)}",file=sys.stderr)

    pop={}
    with ThreadPoolExecutor(max_workers=24) as ex:
        futs={ex.submit(resolve_mint,m):m for m in pop_mints}
        done=0
        for f in as_completed(futs):
            m,c=f.result(); pop[m]=c; done+=1
            if done%200==0: print(f"  pop {done}/{len(pop_mints)}",file=sys.stderr)

    out={"picks":picks,"pop":pop}
    json.dump(out,open("/root/creators_resolved.json","w"))
    pc=set(c for c in picks.values() if c)
    poc=set(c for c in pop.values() if c)
    print(f"DONE picks_creators_unique={len(pc)} pop_creators_unique={len(poc)} union={len(pc|poc)}",file=sys.stderr)
    print(f"picks null={sum(1 for c in picks.values() if not c)} pop null={sum(1 for c in pop.values() if not c)}",file=sys.stderr)

if __name__=="__main__": main()
