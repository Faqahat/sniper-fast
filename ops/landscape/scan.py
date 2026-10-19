#!/usr/bin/env python3
"""Landscape scan: pull a window of recent blocks, tally program activity, detect arb/MEV/pump archetypes."""
import os,json,urllib.request,threading,time,collections,sys
tok=[l.split("=",1)[1].strip() for l in open("/root/arbx/deploy/.env") if l.startswith("CONSTANTK_TOKEN")][0]
RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={tok}"
CACHE="/root/landscape/blocks"; os.makedirs(CACHE,exist_ok=True)
def rpc(m,p,timeout=90):
    b=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode()
    for a in range(6):
        try:
            r=json.load(urllib.request.urlopen(urllib.request.Request(RPC,data=b,headers={"Content-Type":"application/json"}),timeout=timeout))
            if "result" in r: return r["result"]
            return None
        except Exception as e:
            time.sleep(0.5*(a+1))
    return None
def getblock(slot):
    f=f"{CACHE}/{slot}.json"
    if os.path.exists(f):
        try: return json.load(open(f))
        except: pass
    b=rpc("getBlock",[slot,{"encoding":"jsonParsed","transactionDetails":"full","maxSupportedTransactionVersion":1,"rewards":True}])
    try: json.dump(b,open(f,"w"))
    except: pass
    return b

# known programs
PROG={
"6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P":"pumpfun_bc",
"pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA":"pumpswap_amm",
"675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8":"raydium_ammv4",
"CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK":"raydium_clmm",
"CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C":"raydium_cpmm",
"routeUGWgWzqBWFcrCfv8tritsqukccJPu3q5GPP3xS":"raydium_route",
"JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4":"jupiter_v6",
"JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB":"jupiter_v4",
"LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo":"meteora_dlmm",
"whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc":"orca_whirlpool",
"Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB":"meteora_pools",
"dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN":"meteora_dbc",
"5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j":"raydium_launchlab",
"CPMDWBwJDtYax9qW7AyRuVC19Cc4L4Vcy4n2BHAbHkCW":"token_prog",
"TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM":"pump_mintauth",
}
# Jito tip accounts
JITO_TIPS=set("""96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5 HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49 DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh ADuUkR4vqLUMWXxW9gh6D6L8pGm 3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT 3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT""".split())
# arb detection program set (swap venues)
SWAP_VENUES={"pumpfun_bc","pumpswap_amm","raydium_ammv4","raydium_clmm","raydium_cpmm","meteora_dlmm","orca_whirlpool","meteora_pools","raydium_launchlab"}
WSOL="So11111111111111111111111111111111111111112"

def process_block(b,agg):
    if not b: return
    slot=b.get("parentSlot",0)+1
    for tx in b.get("transactions",[]):
        meta=tx.get("meta") or {}
        if meta.get("err"): 
            agg["tx_failed"]+=1; continue
        agg["tx_ok"]+=1
        msg=tx["transaction"]["message"]
        acct=[k["pubkey"] if isinstance(k,dict) else k for k in msg["accountKeys"]]
        signer=acct[0] if acct else None
        # gather program ids across top + inner
        progs=set()
        for ix in msg.get("instructions",[]):
            pid=ix.get("programId")
            if pid: progs.add(pid)
        for inner in meta.get("innerInstructions",[]):
            for ix in inner.get("instructions",[]):
                pid=ix.get("programId")
                if pid: progs.add(pid)
        named={PROG[p] for p in progs if p in PROG}
        for n in named: agg["prog"][n]+=1
        venues=named & SWAP_VENUES
        # jito tip?
        tip=0
        for ix in msg.get("instructions",[]):
            pr=ix.get("parsed")
            if isinstance(pr,dict) and pr.get("type")=="transfer":
                info=pr.get("info",{})
                if info.get("destination") in JITO_TIPS:
                    tip+=int(info.get("lamports",0))
        if tip>0: agg["jito_tx"]+=1; agg["jito_tips_lamports"]+=tip
        # signer SOL delta
        sol_delta=0
        if signer and signer in acct:
            i=acct.index(signer)
            try: sol_delta=(meta["postBalances"][i]-meta["preBalances"][i])
            except: sol_delta=0
        fee=meta.get("fee",0)
        # ARB heuristic: >=2 distinct swap venues OR same venue multiple pools, signer net SOL up after fee
        if len(venues)>=1:
            agg["swap_tx"]+=1
            for v in venues: agg["venue_tx"][v]+=1
        if len(venues)>=2:
            agg["multivenue_tx"]+=1
            # candidate cross-venue arb
            net=sol_delta  # already includes fee effect on signer balance
            agg["arb_cand"].append({"slot":slot,"sig":tx["transaction"]["signatures"][0],"signer":signer,"venues":sorted(venues),"net_lamports":net,"fee":fee,"tip":tip})
        # pump create detection
        if "pump_mintauth" in named or ("pumpfun_bc" in named and any((ix.get("data","")[:1] in ("d","1")) for ix in msg.get("instructions",[]) if ix.get("programId")=="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")):
            pass
    agg["blocks"]+=1

def main():
    tip=rpc("getSlot",[{"commitment":"finalized"}])
    N=int(sys.argv[1]) if len(sys.argv)>1 else 120
    start=tip-N-20
    slots=list(range(start,start+N))
    agg={"prog":collections.Counter(),"venue_tx":collections.Counter(),"blocks":0,"tx_ok":0,"tx_failed":0,
         "swap_tx":0,"multivenue_tx":0,"jito_tx":0,"jito_tips_lamports":0,"arb_cand":[]}
    lock=threading.Lock()
    results={}
    def worker(s):
        b=getblock(s)
        with lock: results[s]=b
    ths=[]
    for s in slots:
        t=threading.Thread(target=worker,args=(s,)); t.start(); ths.append(t)
        if len(ths)>=16:
            for t in ths: t.join()
            ths=[]
    for t in ths: t.join()
    got=0
    for s in slots:
        if results.get(s): got+=1; process_block(results[s],agg)
    agg["slots_requested"]=N; agg["slots_got"]=got; agg["slot_start"]=start; agg["slot_end"]=start+N; agg["tip"]=tip
    agg["prog"]=dict(agg["prog"]); agg["venue_tx"]=dict(agg["venue_tx"])
    # keep only top arb candidates by net
    agg["arb_cand"].sort(key=lambda x:-x["net_lamports"])
    agg["n_arb_cand"]=len(agg["arb_cand"])
    agg["arb_cand"]=agg["arb_cand"][:400]
    json.dump(agg,open("/root/landscape/scan.json","w"))
    print("blocks",agg["blocks"],"tx_ok",agg["tx_ok"],"failed",agg["tx_failed"])
    print("swap_tx",agg["swap_tx"],"multivenue_tx",agg["multivenue_tx"],"jito_tx",agg["jito_tx"],"jito_tips_SOL",round(agg["jito_tips_lamports"]/1e9,2))
    print("PROG:",json.dumps(agg["prog"],indent=0))
    print("VENUE:",json.dumps(agg["venue_tx"],indent=0))
main()
