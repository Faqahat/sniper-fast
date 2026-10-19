import sys,os,json
sys.path.insert(0,"/root/profit_backtest"); import common as C
from concurrent.futures import ThreadPoolExecutor
CB="ComputeBudget111111111111111111111111111111"
PUMP=C.PUMP_B58
a=json.load(open("attempted_feat.json"))
nf=[r for r in a if not r.get("create_found")]
print("recovering",len(nf),flush=True)
def create_cu_from(ix_list):
    for ix in ix_list:
        if ix.get("programId")==CB:
            raw=C.b58dec(ix.get("data",""))
            if raw and raw[0]==3: return int.from_bytes(raw[1:9],"little")
    return 0
def find_create(mint,hint):
    for slot in (hint-1,hint,hint-2):
        blk=C.rpc("getBlock",[slot,{"encoding":"jsonParsed","transactionDetails":"full","maxSupportedTransactionVersion":1,"rewards":False}])
        if not blk: continue
        for tx in blk.get("transactions",[]):
            msg=tx["transaction"]["message"]
            keys=[k["pubkey"] if isinstance(k,dict) else k for k in msg["accountKeys"]]
            la=(tx.get("meta") or {}).get("loadedAddresses") or {}
            allk=keys+list(la.get("writable",[]))+list(la.get("readonly",[]))
            if mint not in allk: continue
            for ix in msg.get("instructions",[]):
                if ix.get("programId")!=PUMP: continue
                dd=C.b58dec(ix.get("data",""))
                if dd[:8].hex() in (C.CREATE_V2,C.CREATE):
                    tx["slot"]=slot
                    f=C.parse_create(tx)
                    if f:
                        f["create_cu_price"]=create_cu_from(msg.get("instructions",[]))
                        return f
    return None
def work(r):
    f=find_create(r["mint"],r["his_first_slot"])
    return (r["mint"],f)
rec={}
with ThreadPoolExecutor(max_workers=12) as ex:
    for m,f in ex.map(work,nf):
        rec[m]=f
got=0
for r in a:
    if r.get("create_found"): continue
    f=rec.get(r["mint"])
    if f:
        got+=1
        r.update({"create_found":True,"create_slot":f.get("create_slot"),"creator":f.get("creator"),
            "mayhem":f.get("mayhem"),"cashback":f.get("cashback"),"creator_fee_bps":f.get("creator_fee_bps"),
            "holder_reward":f.get("holder_reward"),"dev_buy":f.get("dev_buy"),"dev_buy_wire":f.get("dev_buy_wire"),
            "token_recv":f.get("token_recv"),"entry_px":f.get("entry_px"),"create_cu_price":f.get("create_cu_price"),
            "is_v2":f.get("is_v2")})
        r["buy_delta"]=r["his_first_slot"]-f.get("create_slot") if f.get("create_slot") else None
json.dump(a,open("attempted_feat.json","w"),indent=0)
print("recovered",got,"now create_found",sum(1 for r in a if r.get("create_found")),"/",len(a),flush=True)
