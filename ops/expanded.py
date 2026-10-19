import os, json, time, urllib.request, urllib.error, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

RPC="https://rpc-frankfurt.constant-k.com/?api-key="+os.environ["CONSTANTK_TOKEN"]
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
WSOL="So11111111111111111111111111111111111111112"
TARGET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
RENT=1_493_520

def rpc(method,params,tries=9):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    last=None
    for t in range(tries):
        try:
            req=urllib.request.Request(RPC,data=body,headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req,timeout=45) as r: j=json.loads(r.read())
            if "error" in j:
                last=j["error"]
                if isinstance(last,dict) and last.get("code")==-32015: return ("__VERR__",last)
                time.sleep(0.4*(t+1)); continue
            return j.get("result")
        except urllib.error.HTTPError as e:
            last=e; time.sleep(1.0+0.8*t if e.code==429 else 0.5*(t+1))
        except Exception as e:
            last=e; time.sleep(0.5*(t+1))
    raise RuntimeError(f"fail {method}: {last}")

def get_tx(sig):
    for v in (0,1,2,3,10):
        res=rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":v,"encoding":"jsonParsed"}])
        if isinstance(res,tuple) and res and res[0]=="__VERR__": continue
        return res
    return None

def all_sigs(addr):
    out=[]; before=None
    while True:
        p=[addr,{"limit":1000}]
        if before: p[1]["before"]=before
        r=rpc("getSignaturesForAddress",p)
        if not r: break
        out+=r; before=r[-1]["signature"]
        if len(r)<1000:
            # confirm end
            r2=rpc("getSignaturesForAddress",[addr,{"limit":1000,"before":before}])
            if not r2: break
            out+=r2; before=r2[-1]["signature"]
            if len(r2)<1000 and not r2: break
            if len(r2)<1: break
            if len(r2)<1000: break
    return out

def is_pump_buy(tx):
    if not tx or tx.get("meta",{}).get("err") is not None: return False
    logs=tx.get("meta",{}).get("logMessages") or []
    if not any(PUMP in l for l in logs): return False
    txt=" ".join(logs)
    return ("Instruction: Buy" in txt) or ("BuyExactQuote" in txt)

def buy_mint(tx):
    meta=tx.get("meta",{})
    pre={(b["owner"],b["mint"]):float(b["uiTokenAmount"]["amount"]) for b in meta.get("preTokenBalances",[])}
    best=None;bd=0
    for b in meta.get("postTokenBalances",[]):
        if b.get("owner")!=TARGET or b["mint"]==WSOL: continue
        d=float(b["uiTokenAmount"]["amount"])-pre.get((TARGET,b["mint"]),0.0)
        if d>bd: bd=d;best=b["mint"]
    return best

def resolve_create(mint):
    try:
        s=all_sigs(mint)
        if not s: return (mint,{"status":"no_sigs"})
        oldest=s[-1]["signature"]
        ctx=get_tx(oldest)
        if not ctx: return (mint,{"status":"no_ctx"})
        meta=ctx.get("meta",{}); msg=ctx["transaction"]["message"]
        pubs=[k["pubkey"] if isinstance(k,dict) else k for k in msg.get("accountKeys",[])]
        pre=meta.get("preBalances",[]); post=meta.get("postBalances",[])
        logs=meta.get("logMessages") or []
        has_create=any("Instruction: Create" in l for l in logs)
        pump_prog=any(PUMP in l for l in logs)
        gm=rpc("getMultipleAccounts",[pubs,{"encoding":"base64"}])
        best=None
        for i,acc in enumerate(gm.get("value") or []):
            if acc and acc.get("owner")==PUMP and i<len(pre) and i<len(post):
                gain=post[i]-pre[i]
                if gain>0 and (best is None or gain>best[0]): best=(gain,i)
        info={"status":"ok","has_create_log":has_create,"pump_in_logs":pump_prog}
        info["curve_gain_lamports"]=best[0] if best else None
        info["dev_buy_sol"]=((best[0]-RENT)/1e9) if best else (0.0 if has_create else None)
        return (mint,info)
    except Exception as e:
        return (mint,{"status":f"err:{e}"})

def main():
    want=1000
    print("paging all sigs...",file=sys.stderr)
    sigs=all_sigs(TARGET)
    landed=[s["signature"] for s in sigs if s.get("err") is None]
    print(f"total sigs={len(sigs)} landed={len(landed)}",file=sys.stderr)

    # classify buys in parallel
    def work(sig):
        try:
            tx=get_tx(sig)
            if is_pump_buy(tx): return (sig,buy_mint(tx))
        except Exception: return (sig,None)
        return (sig,None)
    res={}
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs={ex.submit(work,s):s for s in landed}
        done=0
        for f in as_completed(futs):
            sig,m=f.result(); res[sig]=m; done+=1
            if done%250==0: print(f"  classify {done}/{len(landed)}",file=sys.stderr)
    mints=[]; seen=set()
    for sig in landed:  # newest-first
        m=res.get(sig)
        if m and m not in seen: seen.add(m); mints.append(m)
    print(f"unique buy mints found={len(mints)}",file=sys.stderr)
    mints=mints[:want]
    json.dump(mints,open("/root/expanded_mints.json","w"))

    # reuse cache
    cache={}
    try: cache=json.load(open("/root/devbuy2_raw.json"))
    except Exception: pass
    todo=[m for m in mints if m not in cache or cache[m].get("status")!="ok"]
    print(f"to resolve (not cached)={len(todo)} ; cached ok={len(mints)-len(todo)}",file=sys.stderr)
    out={m:cache[m] for m in mints if m in cache and cache[m].get("status")=="ok"}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs={ex.submit(resolve_create,m):m for m in todo}
        done=0
        for f in as_completed(futs):
            m,info=f.result(); out[m]=info; done+=1
            if done%100==0: print(f"  resolve {done}/{len(todo)}",file=sys.stderr)
    json.dump(out,open("/root/expanded_raw.json","w"),indent=0)
    print("saved expanded_raw.json",file=sys.stderr)

if __name__=="__main__": main()
