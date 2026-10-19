import sys, json, hashlib, base64, threading
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
sys.path.insert(0,"/root/tmp_creator")
from analyze import rpc, b58decode, PUMP, CREATOR
PUMPSWAP="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
WSOL="So11111111111111111111111111111111111111112"
DISC={
 hashlib.sha256(b"global:create").digest()[:8].hex():"create",
 hashlib.sha256(b"global:buy").digest()[:8].hex():"buy",
 hashlib.sha256(b"global:sell").digest()[:8].hex():"sell",
}
sigs=json.load(open("/root/tmp_creator/sigs.json"))
succ=[s["signature"] for s in sigs if not s.get("err")]

lock=threading.Lock()
role=Counter(); instr=Counter(); done=[0]
mint_trade=Counter()   # mints bwamJz trades as fp
mint_fp_buy=Counter()

def work(sig):
    tx=rpc("getTransaction",[sig,{"encoding":"jsonParsed","maxSupportedTransactionVersion":0}])
    if not tx: 
        with lock: done[0]+=1
        return
    msg=tx["transaction"]["message"]
    keys=[ (k.get("pubkey") if isinstance(k,dict) else k) for k in msg["accountKeys"]]
    fp=keys[0]; isfp=(fp==CREATOR)
    instrs=list(msg.get("instructions",[]))
    for inner in tx.get("meta",{}).get("innerInstructions",[]) or []:
        instrs+=inner.get("instructions",[])
    kinds=set()
    for ix in instrs:
        pid=ix.get("programId")
        if pid==PUMP and "data" in ix:
            try: h=b58decode(ix["data"])[:8].hex()
            except: continue
            kinds.add("pump:"+DISC.get(h,h[:6]))
        elif pid==PUMPSWAP:
            kinds.add("pumpswap")
    # mints from token balances
    tb=(tx.get("meta",{}).get("postTokenBalances") or [])+(tx.get("meta",{}).get("preTokenBalances") or [])
    mints=set(b.get("mint") for b in tb if b.get("mint") and b.get("mint")!=WSOL)
    with lock:
        done[0]+=1
        role["fp_bwam" if isfp else "referenced"]+=1
        for k in kinds: instr[k]+=1
        if isfp:
            for m in mints: mint_trade[m]+=1
            if any("buy" in k for k in kinds):
                for m in mints: mint_fp_buy[m]+=1
        if done[0]%800==0:
            print("done",done[0],flush=True)

with ThreadPoolExecutor(max_workers=24) as ex:
    list(ex.map(work, succ))

print("ROLE:",dict(role))
print("INSTR:",dict(instr.most_common()))
print("distinct mints bwam trades (as fp):",len(mint_trade))
print("distinct mints bwam BUYS (as fp):",len(mint_fp_buy))
json.dump(dict(mint_trade),open("/root/tmp_creator/mint_trade.json","w"))
json.dump(dict(mint_fp_buy),open("/root/tmp_creator/mint_fp_buy.json","w"))
print("top traded mints:")
for m,c in mint_trade.most_common(15): print("  ",m,c)
