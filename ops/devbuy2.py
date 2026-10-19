import os, json, time, urllib.request, urllib.error, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

RPC = "https://rpc-frankfurt.constant-k.com/?api-key=" + os.environ["CONSTANTK_TOKEN"]
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
WSOL = "So11111111111111111111111111111111111111112"
TARGET = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
RENT = 1_461_600

def rpc(method, params, tries=9):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    last=None
    for t in range(tries):
        try:
            req=urllib.request.Request(RPC,data=body,headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req,timeout=45) as r:
                j=json.loads(r.read())
            if "error" in j:
                last=j["error"]
                # version error -> signal caller
                if isinstance(last,dict) and last.get("code")==-32015:
                    return ("__VERR__", last)
                time.sleep(0.4*(t+1)); continue
            return j.get("result")
        except urllib.error.HTTPError as e:
            last=e
            if e.code==429: time.sleep(1.0+0.8*t)
            else: time.sleep(0.5*(t+1))
        except Exception as e:
            last=e; time.sleep(0.5*(t+1))
    raise RuntimeError(f"rpc fail {method}: {last}")

def get_tx(sig):
    for v in (0,1,2,3,10):
        res=rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":v,"encoding":"jsonParsed"}])
        if isinstance(res,tuple) and res and res[0]=="__VERR__":
            continue
        return res
    return None

def get_sigs_all(addr):
    out=[]; before=None
    while True:
        p=[addr,{"limit":1000}]
        if before: p[1]["before"]=before
        r=rpc("getSignaturesForAddress",p)
        if not r: break
        out+=r; before=r[-1]["signature"]
        if len(r)<1000: break
    return out

def resolve_create(mint):
    try:
        allsigs=get_sigs_all(mint)
        if not allsigs: return (mint,{"status":"no_sigs"})
        oldest=allsigs[-1]["signature"]
        ctx=get_tx(oldest)
        if not ctx: return (mint,{"status":"no_ctx","n_sigs":len(allsigs)})
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
                if gain>0 and (best is None or gain>best[0]):
                    best=(gain,i,pubs[i])
        info={"status":"ok","create_sig":oldest,"n_sigs":len(allsigs),
              "has_create_log":has_create,"pump_in_logs":pump_prog,
              "is_pump_mint":mint.endswith("pump")}
        if best:
            info["curve_gain_lamports"]=best[0]
            info["dev_buy_sol"]=(best[0]-RENT)/1e9
            info["method"]="curve"
        else:
            info["dev_buy_sol"]=0.0 if has_create else None
            info["method"]="no_curve_found"
        return (mint,info)
    except Exception as e:
        return (mint,{"status":f"err:{e}"})

def main():
    mints=list(json.load(open("/root/devbuy_raw.json")).keys())
    print(f"re-resolving {len(mints)} mints", file=sys.stderr)
    out={}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs={ex.submit(resolve_create,m):m for m in mints}
        done=0
        for f in as_completed(futs):
            m,info=f.result(); out[m]=info; done+=1
            if done%25==0: print(f"  {done}/{len(mints)}",file=sys.stderr)
    json.dump(out,open("/root/devbuy2_raw.json","w"),indent=0)

    ok=[(m,i) for m,i in out.items() if i.get("status")=="ok"]
    fails=[(m,i.get("status")) for m,i in out.items() if i.get("status")!="ok"]
    print(f"resolved ok: {len(ok)}  fails: {len(fails)}",file=sys.stderr)
    print("fail reasons:", {s: sum(1 for _,x in fails if x==s) for s in set(x for _,x in fails)} if fails else {}, file=sys.stderr)

    # separate pump mints from non-pump, and real dev buys
    pump_ok=[(m,i) for m,i in ok if i.get("is_pump_mint") and i.get("has_create_log")]
    nonpump=[(m,i) for m,i in ok if not i.get("is_pump_mint")]
    print(f"pump create-confirmed: {len(pump_ok)} ; non-pump mints: {len(nonpump)}", file=sys.stderr)

    import statistics as st
    def pct(a,q):
        if not a: return None
        i=(len(a)-1)*q; lo=int(i); hi=min(lo+1,len(a)-1)
        return a[lo]+(a[hi]-a[lo])*(i-lo)
    def report(vals,label):
        a=sorted(v for v in vals if v is not None)
        if not a: print(f"\n[{label}] empty"); return
        print(f"\n[{label}] n={len(a)}")
        print(f"  min={a[0]:.3f} p10={pct(a,.1):.3f} p25={pct(a,.25):.3f} median={st.median(a):.3f} p75={pct(a,.75):.3f} p90={pct(a,.9):.3f} max={a[-1]:.3f} mean={st.mean(a):.3f}")
        for usd in (180,220):
            print(f"  @${usd}: median ${st.median(a)*usd:.0f} | p25-p75 ${pct(a,.25)*usd:.0f}-${pct(a,.75)*usd:.0f} | p10-p90 ${pct(a,.1)*usd:.0f}-${pct(a,.9)*usd:.0f}")
        from collections import Counter
        c=Counter()
        for v in a: c[int(v//0.25)]+=1
        for b in sorted(c):
            lo=b*0.25; print(f"    {lo:5.2f}-{lo+0.25:5.2f}: {'#'*c[b]} {c[b]}")
        n=len(a)
        print(f"  in 1.5-1.75 SOL: {sum(1 for v in a if 1.5<=v<1.75)} ({100*sum(1 for v in a if 1.5<=v<1.75)/n:.0f}%)")
        print(f"  <0.5: {100*sum(1 for v in a if v<0.5)/n:.0f}%  0.5-1.0: {100*sum(1 for v in a if 0.5<=v<1.0)/n:.0f}%  1.0-2.0: {100*sum(1 for v in a if 1.0<=v<2.0)/n:.0f}%  >=2.0: {100*sum(1 for v in a if v>=2.0)/n:.0f}%")
        print(f"  ==0 exactly: {sum(1 for v in a if v==0)}")

    allvals=[i.get("dev_buy_sol") for _,i in ok]
    report([v for v in allvals if v is not None],"ALL OK (incl non-pump & zeros)")
    report([i.get("dev_buy_sol") for _,i in pump_ok],"PUMP CREATE-CONFIRMED (incl zeros)")
    report([i.get("dev_buy_sol") for _,i in pump_ok if i.get("dev_buy_sol",0)>0],"PUMP CREATE-CONFIRMED, dev_buy>0")

if __name__=="__main__":
    main()
