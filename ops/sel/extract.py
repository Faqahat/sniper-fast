import os, json, time, urllib.request, urllib.error, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

RPC="https://rpc-frankfurt.constant-k.com/?api-key="+os.environ["CONSTANTK_TOKEN"]
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
WSOL="So11111111111111111111111111111111111111112"
TARGET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
RENT=1_493_520

def rpc(method,params,tries=7):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    last=None
    for t in range(tries):
        try:
            req=urllib.request.Request(RPC,data=body,headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req,timeout=40) as r: j=json.loads(r.read())
            if "error" in j:
                last=j["error"]
                if isinstance(last,dict) and last.get("code")==-32015: return ("__VERR__",last)
                time.sleep(0.3*(t+1)); continue
            return j.get("result")
        except urllib.error.HTTPError as e:
            last=e; time.sleep(0.8+0.6*t if e.code==429 else 0.4*(t+1))
        except Exception as e:
            last=e; time.sleep(0.4*(t+1))
    return ("__FAIL__",str(last))

def get_tx(sig):
    for v in (0,):
        res=rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
        if isinstance(res,tuple) and res and res[0]=="__VERR__": continue
        return res
    return None

def sigs_page(addr, before=None, limit=1000):
    p=[addr,{"limit":limit}]
    if before: p[1]["before"]=before
    r=rpc("getSignaturesForAddress",p)
    if isinstance(r,tuple): return []
    return r or []

def oldest_sigs(mint, max_pages=6):
    """page to the oldest; return (oldest_sig, tail_list) where tail_list is the last page (oldest, newest-first)."""
    before=None; last_page=[]; pages=0; total=0
    while pages<max_pages:
        r=sigs_page(mint, before=before)
        pages+=1
        if not r: break
        total+=len(r); last_page=r
        if len(r)<1000: break
        before=r[-1]["signature"]
    capped = (pages>=max_pages and len(last_page)==1000)
    return last_page, total, capped

def curve_gain_from_tx(tx):
    """sum positive lamport gain of pump-owned accounts (bonding curve). returns (gain_lamports, slot, feepayer, blocktime)"""
    meta=tx.get("meta",{}); msg=tx["transaction"]["message"]
    pubs=[k["pubkey"] if isinstance(k,dict) else k for k in msg.get("accountKeys",[])]
    pre=meta.get("preBalances",[]); post=meta.get("postBalances",[])
    feepayer=pubs[0] if pubs else None
    return pubs, pre, post, feepayer

def analyze_token(mint, known_create_sig=None):
    out={"mint":mint}
    try:
        last_page, total_sigs, capped = oldest_sigs(mint)
        if not last_page:
            out["status"]="no_sigs"; return out
        # oldest sig = tail of last_page (newest-first ordering within page)
        oldest = last_page[-1]
        create_sig = oldest["signature"]
        out["create_sig"]=create_sig
        out["total_sigs_pages"]=total_sigs
        out["sigs_capped"]=capped
        ctx = get_tx(create_sig)
        if not ctx:
            out["status"]="no_ctx"; return out
        meta=ctx.get("meta",{}) or {}
        slot=ctx.get("slot"); bt=ctx.get("blockTime")
        out["create_slot"]=slot; out["block_time"]=bt
        logs=meta.get("logMessages") or []
        out["has_create_log"]=any("Instruction: Create" in l for l in logs)
        msg=ctx["transaction"]["message"]
        pubs=[k["pubkey"] if isinstance(k,dict) else k for k in msg.get("accountKeys",[])]
        feepayer=pubs[0] if pubs else None
        out["creator"]=feepayer
        pre=meta.get("preBalances",[]); post=meta.get("postBalances",[])
        # dev buy = pump-owned account max positive gain minus rent
        gm=rpc("getMultipleAccounts",[pubs,{"encoding":"base64"}])
        best=None
        if not isinstance(gm,tuple) and gm:
            for i,acc in enumerate(gm.get("value") or []):
                if acc and acc.get("owner")==PUMP and i<len(pre) and i<len(post):
                    gain=post[i]-pre[i]
                    if gain>0 and (best is None or gain>best): best=gain
        out["dev_buy_sol"]=((best-RENT)/1e9) if best else (0.0 if out["has_create_log"] else None)
        # name/symbol length from create instruction (parse borsh from pump program ix data)
        out["name_len"]=None; out["symbol_len"]=None
        # count create-tx inner buy instructions (num buy ix in create tx itself)
        txt=" ".join(logs)
        out["buys_in_create_tx"]=txt.count("Instruction: Buy")
        # co-bundlers: sigs in the SAME slot as create (excluding create), buys, distinct signers + bundled sol
        same_slot=[s for s in last_page if s.get("slot")==slot and s["signature"]!=create_sig and s.get("err") is None]
        out["n_same_slot_sigs"]=len(same_slot)
        cob_signers=set(); cob_sol=0.0; cob_buys=0
        for s in same_slot[:25]:
            t=get_tx(s["signature"])
            if not t: continue
            tl=t.get("meta",{}).get("logMessages") or []
            if not any(PUMP in l for l in tl): continue
            ttxt=" ".join(tl)
            if "Instruction: Buy" not in ttxt: continue
            cob_buys+=1
            tm=t["transaction"]["message"]
            tp=[k["pubkey"] if isinstance(k,dict) else k for k in tm.get("accountKeys",[])]
            if tp: cob_signers.add(tp[0])
            # sol into curve this tx
            tpre=t.get("meta",{}).get("preBalances",[]); tpost=t.get("meta",{}).get("postBalances",[])
            tgm=None
            # cheap: fee payer lamport drop as proxy for buy size
            if tpre and tpost: cob_sol += max(0,(tpre[0]-tpost[0]))/1e9
        out["n_cobundlers"]=len(cob_signers)
        out["cobundler_buys_same_slot"]=cob_buys
        out["cobundler_sol_proxy"]=round(cob_sol,4)
        out["total_bundled_sol"]=round((out["dev_buy_sol"] or 0)+cob_sol,4)
        out["status"]="ok"
        return out
    except Exception as e:
        out["status"]=f"err:{e}"; return out

def creator_history(creator, create_slot):
    try:
        r=sigs_page(creator, limit=1000)
        if not r: return {"creator_total_sigs":0,"creator_prior_sigs":0,"creator_age_slots":0,"creator_capped":False}
        slots=[s.get("slot") for s in r if s.get("slot")]
        prior=sum(1 for s in slots if s<create_slot)
        oldest=min(slots) if slots else create_slot
        return {"creator_total_sigs":len(r),
                "creator_prior_sigs":prior,
                "creator_age_slots":max(0,create_slot-oldest),
                "creator_capped": len(r)>=1000}
    except Exception as e:
        return {"creator_err":str(e)}

def main():
    label=sys.argv[1]  # pos or neg
    mints=json.load(open(sys.argv[2]))
    outpath=sys.argv[3]
    cache={}
    if os.path.exists(outpath):
        try: cache=json.load(open(outpath))
        except Exception: cache={}
    todo=[m for m in mints if m not in cache or cache[m].get("status")!="ok"]
    print(f"[{label}] total={len(mints)} todo={len(todo)} cached_ok={len(mints)-len(todo)}",file=sys.stderr)
    out=dict(cache)
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs={ex.submit(analyze_token,m):m for m in todo}
        done=0
        for f in as_completed(futs):
            r=f.result(); out[r["mint"]]=r; done+=1
            if done%50==0:
                json.dump(out,open(outpath,"w"))
                print(f"  [{label}] {done}/{len(todo)}",file=sys.stderr)
    json.dump(out,open(outpath,"w"))
    # creator history for ok tokens (unique creators)
    creators={}
    for m,r in out.items():
        if r.get("status")=="ok" and r.get("creator") and r.get("create_slot"):
            creators.setdefault(r["creator"],[]).append((m,r["create_slot"]))
    print(f"[{label}] unique creators={len(creators)}",file=sys.stderr)
    chist={}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs={ex.submit(creator_history,c,min(s for _,s in lst)):c for c,lst in creators.items()}
        done=0
        for f in as_completed(futs):
            c=futs[f]; chist[c]=f.result(); done+=1
            if done%50==0: print(f"  [{label}] creators {done}/{len(creators)}",file=sys.stderr)
    for m,r in out.items():
        if r.get("creator") in chist: r.update(chist[r["creator"]])
    json.dump(out,open(outpath,"w"))
    print(f"[{label}] DONE saved {outpath}",file=sys.stderr)

if __name__=="__main__": main()
