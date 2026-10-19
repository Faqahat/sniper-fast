import sys, json, hashlib, base64, threading, struct
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
sys.path.insert(0,"/root/tmp_creator")
from analyze import rpc, b58decode, b58encode, bonding_curve, PUMP, CREATOR
PUMPSWAP="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
WSOL="So11111111111111111111111111111111111111112"
sigs=json.load(open("/root/tmp_creator/sigs.json"))
succ=[s["signature"] for s in sigs if not s.get("err")]
lock=threading.Lock()
ref_mints=Counter()   # mints from txs where bwam is NOT fp but involves pump bonding curve
done=[0]
def work(sig):
    tx=rpc("getTransaction",[sig,{"encoding":"jsonParsed","maxSupportedTransactionVersion":0}])
    if not tx:
        with lock: done[0]+=1
        return
    msg=tx["transaction"]["message"]
    keys=[(k.get("pubkey") if isinstance(k,dict) else k) for k in msg["accountKeys"]]
    isfp=(keys[0]==CREATOR)
    instrs=list(msg.get("instructions",[]))
    for inner in tx.get("meta",{}).get("innerInstructions",[]) or []:
        instrs+=inner.get("instructions",[])
    has_pump=any(ix.get("programId")==PUMP for ix in instrs)
    tb=(tx.get("meta",{}).get("postTokenBalances") or [])
    mints=set(b.get("mint") for b in tb if b.get("mint") and b.get("mint")!=WSOL)
    with lock:
        done[0]+=1
        if (not isfp) and has_pump:
            for m in mints: ref_mints[m]+=1
with ThreadPoolExecutor(max_workers=24) as ex:
    list(ex.map(work, succ))
print("distinct pump-bonding-curve mints in REFERENCED(non-fp) txs:",len(ref_mints),flush=True)

# check curve creator for these mints
cand=[m for m,_ in ref_mints.most_common(120)]
match=0; checked=0; outcomes=Counter(); rs_list=[]
def chk(m):
    bc=bonding_curve(m)
    ai=rpc("getAccountInfo",[bc,{"encoding":"base64","commitment":"confirmed"}])
    v=ai.get("value") if ai else None
    if not v: return (m,"migrated",None,None)
    raw=base64.b64decode(v["data"][0])
    if len(raw)<81: return (m,"short",None,None)
    rs=struct.unpack_from("<Q",raw,32)[0]/1e9
    complete=raw[48]
    creator=b58encode(raw[49:81])
    return (m,"complete" if complete else "active",rs,creator)
with ThreadPoolExecutor(max_workers=12) as ex:
    for m,st,rs,creator in ex.map(chk,cand):
        checked+=1
        if creator==CREATOR: match+=1
json.dump(dict(ref_mints),open("/root/tmp_creator/ref_mints.json","w"))
print(f"checked {checked} referenced mints -> curve_creator==bwamJz: {match}")
