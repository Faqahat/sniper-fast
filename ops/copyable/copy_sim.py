#!/usr/bin/env python3
"""STEP 3 copy-ability simulation.
For each candidate wallet (that has a tape), measure the realistic COPY entry at 1-2
slot lag and compute net copy-R vs mirroring the wallet's own exit.

Method:
 1. Load tape (/root/copyable/tapes/<w>.json). Take closed positions (buy+sell paired).
 2. LAG MULTIPLIER (empirical): sample up to N first-buys. For each, fetch blocks at
    buy_slot+1 and buy_slot+2, scan pump/pumpswap trades on that mint, take the implied
    price of the nearest print after their buy. lag_mult = price_lag / their_buy_px.
    No print in window -> price didn't move -> lag_mult = 1.0 (copyable, no competition).
 3. COPY net-R per position: their realized r_mult already nets pump 1% fee + their slip
    (from balance deltas). Copying, we pay lag_mult more on entry, same pump fee, plus our
    own priority fee. copy_r_mult = their_r_mult / lag_mult ; net = copy_r_mult - 1 - prio_drag.
    prio_drag = legs*(prio_lam+base_lam)/1e9 / SIZE.
 4. Report copy mean/median net-R, win%, total, drawdown-ish, trades/day.
Usage: python3 copy_sim.py <wallet> [SIZE_SOL] [N_SAMPLE]
"""
import requests, json, sys, time, statistics as st
from concurrent.futures import ThreadPoolExecutor

RPC=open('/root/snipe_study50/rpc_url.txt').read().strip()
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMPSWAP="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
WSOL="So11111111111111111111111111111111111111112"
DEX_PROGS={PUMP,PUMPSWAP,
 "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8","CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK",
 "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C","JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",
 "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo","Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB",
 "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"}
PRIO_LAM=360_000; BASE_LAM=5_000

sess=requests.Session()
def rpc(method,params,tries=5):
    for i in range(tries):
        try:
            r=sess.post(RPC,json={"jsonrpc":"2.0","id":1,"method":method,"params":params},timeout=60)
            j=r.json()
            if 'result' in j: return j['result']
            err=j.get('error',{})
            if err.get('code')==-32007 or 'skip' in str(err).lower(): return None
            if err.get('code') in (-32019,-32005) or 'rate' in str(err).lower(): time.sleep(0.8); continue
            return None
        except Exception: time.sleep(0.6)
    return None

def getblock(slot):
    return rpc("getBlock",[slot,{"maxSupportedTransactionVersion":1,"transactionDetails":"full",
                                  "rewards":False,"encoding":"jsonParsed"}])

def prices_in_block(res, mint):
    """return list of implied prices (SOL/token) for pump/pumpswap trades on mint in this block."""
    out=[]
    if not res: return out
    for tx in res.get("transactions",[]):
        meta=tx.get("meta") or {}
        if meta.get("err") is not None: continue
        msg=tx["transaction"]["message"]
        # program check
        pids=set()
        for ix in msg.get("instructions",[]):
            if ix.get("programId"): pids.add(ix["programId"])
        for inner in meta.get("innerInstructions",[]):
            for ix in inner.get("instructions",[]):
                if ix.get("programId"): pids.add(ix["programId"])
        if not (pids & DEX_PROGS): continue
        # token delta per owner for this mint; WSOL delta per owner
        pre={}; post={}; prew={}; postw={}
        for b in meta.get("preTokenBalances",[]) or []:
            o=b.get("owner")
            if not o: continue
            amt=float(b["uiTokenAmount"].get("uiAmount") or 0)
            if b.get("mint")==mint: pre[o]=amt
            elif b.get("mint")==WSOL: prew[o]=prew.get(o,0)+amt
        for b in meta.get("postTokenBalances",[]) or []:
            o=b.get("owner")
            if not o: continue
            amt=float(b["uiTokenAmount"].get("uiAmount") or 0)
            if b.get("mint")==mint: post[o]=amt
            elif b.get("mint")==WSOL: postw[o]=postw.get(o,0)+amt
        owners=set(pre)|set(post)
        best=None
        for o in owners:
            d=post.get(o,0)-pre.get(o,0)
            if abs(d)>0 and (best is None or abs(d)>abs(best[1])): best=(o,d)
        if not best: continue
        owner,tokd=best
        keys=[k['pubkey'] if isinstance(k,dict) else k for k in msg.get("accountKeys",[])]
        try: oidx=keys.index(owner)
        except ValueError: continue
        preB=meta.get("preBalances",[]); postB=meta.get("postBalances",[])
        if oidx>=len(preB): continue
        lamd=postB[oidx]-preB[oidx]
        if oidx==0: lamd+=meta.get("fee",0) or 0
        sol=abs(lamd/1e9 + (postw.get(owner,0)-prew.get(owner,0)))
        tok=abs(tokd)
        if tok<=0 or sol<=1e-7: continue
        out.append(sol/tok)
    return out

def measure_lag(positions, n_sample=40, lags=(1,2)):
    """For sampled first-buys, fetch post-buy blocks, compute lag multiplier."""
    # positions with a known first_buy_slot and avg_buy_px and a buy before any sell
    cand=[p for p in positions if p.get("first_buy_slot") and p.get("avg_buy_px",0)>0]
    cand.sort(key=lambda p: -(p.get("buy_sol") or 0))  # sample biggest positions (most meaningful)
    cand=cand[:n_sample]
    # gather needed slots
    jobs=[]
    for p in cand:
        for d in lags:
            jobs.append((p["mint"], p["first_buy_slot"]+d, p["first_buy_slot"], p["avg_buy_px"]))
    results={}
    def work(job):
        mint,slot,bs,px=job
        res=getblock(slot)
        pr=prices_in_block(res, mint)
        return (mint,bs,slot,px,pr)
    lag_mults=[]; detail=[]
    # per position, find nearest print after buy across lag slots
    bypos={}
    with ThreadPoolExecutor(max_workers=16) as ex:
        for mint,bs,slot,px,pr in ex.map(work, jobs):
            bypos.setdefault((mint,bs,px),{})[slot]=pr
    for (mint,bs,px),slotmap in bypos.items():
        chosen=None
        for d in lags:
            pr=slotmap.get(bs+d,[])
            if pr:
                chosen=st.median(pr); break
        if chosen is None:
            lag_mults.append(1.0); detail.append({"mint":mint,"their_px":px,"lag_px":None,"mult":1.0,"noprint":True})
        else:
            m=chosen/px if px>0 else 1.0
            # guard absurd (data noise): clamp to [0.3, 20]
            m=max(0.3,min(20.0,m))
            lag_mults.append(m); detail.append({"mint":mint,"their_px":px,"lag_px":chosen,"mult":m})
    return lag_mults, detail

def sim(wallet, SIZE=0.5, n_sample=40):
    T=json.load(open(f"/root/copyable/tapes/{wallet}.json"))
    positions=T["positions"]
    closed=[p for p in positions if p.get("sell_tok",0)>0 and p.get("buy_sol",0)>0 and p.get("r_mult")]
    lag_mults, detail=measure_lag(positions, n_sample)
    med_lag=st.median(lag_mults) if lag_mults else 1.0
    mean_lag=sum(lag_mults)/len(lag_mults) if lag_mults else 1.0
    frac_moved=sum(1 for m in lag_mults if m>1.05)/len(lag_mults) if lag_mults else 0
    # apply per-position: use med_lag as the copy entry penalty (robust, single multiplier)
    prio_drag=2*(PRIO_LAM+BASE_LAM)/1e9/SIZE   # buy + 1 sell leg priority
    copy_nets=[]; their_nets=[]
    for p in closed:
        their_r=p["r_mult"]
        copy_r=their_r/med_lag
        copy_net=copy_r-1-prio_drag
        copy_nets.append(copy_net)
        their_nets.append(their_r-1)
    def summ(xs):
        if not xs: return None
        s=sorted(xs); n=len(xs)
        return {"n":n,"mean":sum(xs)/n,"median":st.median(xs),
                "win":sum(1 for x in xs if x>0)/n,"tot":sum(xs),
                "p10":s[max(0,int(.1*n))],"p90":s[min(n-1,int(.9*n))]}
    out={"wallet":wallet,"size_sol":SIZE,"n_closed":len(closed),
         "lag_sample_n":len(lag_mults),"med_lag_mult":med_lag,"mean_lag_mult":mean_lag,
         "frac_buys_price_moved_gt5pct":frac_moved,"prio_drag_frac":prio_drag,
         "copy_net":summ(copy_nets),"their_net":summ(their_nets),
         "lag_detail":detail[:20]}
    return out

if __name__=="__main__":
    wallet=sys.argv[1]
    SIZE=float(sys.argv[2]) if len(sys.argv)>2 else 0.5
    N=int(sys.argv[3]) if len(sys.argv)>3 else 40
    r=sim(wallet,SIZE,N)
    import os; os.makedirs("/root/copyable/copyres",exist_ok=True)
    json.dump(r, open(f"/root/copyable/copyres/{wallet}.json","w"),indent=1)
    cn=r["copy_net"]; tn=r["their_net"]
    print(f"{wallet}  nClosed={r['n_closed']} medLag={r['med_lag_mult']:.3f} "
          f"fracMoved={r['frac_buys_price_moved_gt5pct']:.2f}")
    if cn:
        print(f"  THEIR net: mean={tn['mean']:.3f} med={tn['median']:.3f} win={tn['win']:.2f} tot={tn['tot']:.2f}")
        print(f"  COPY  net: mean={cn['mean']:.3f} med={cn['median']:.3f} win={cn['win']:.2f} tot={cn['tot']:.2f} (SIZE={SIZE})")
