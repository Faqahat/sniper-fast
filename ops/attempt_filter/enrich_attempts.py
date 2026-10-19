import sys,os,json,time
sys.path.insert(0,"/root/profit_backtest"); import common as C
from concurrent.futures import ThreadPoolExecutor
CB="ComputeBudget111111111111111111111111111111"
att=json.load(open("attempts.json"))["attempts"]
# group his buys per mint
bym={}
for a in att:
    bym.setdefault(a["mint"],[]).append(a)
mints=list(bym.keys())
print("attempted mints:",len(mints),flush=True)
def oldest_sig(mint):
    before=None; last=None
    for _ in range(6):
        pr=[mint,{"limit":1000}]
        if before: pr[1]["before"]=before
        r=C.rpc("getSignaturesForAddress",pr)
        if not r: break
        last=r[-1]; before=r[-1]["signature"]
        if len(r)<1000: break
    return last
def create_cu(tx):
    try:
        msg=tx["transaction"]["message"]
        for ix in msg.get("instructions",[]):
            if ix.get("programId")==CB:
                raw=C.b58dec(ix.get("data",""))
                if raw and raw[0]==3: return int.from_bytes(raw[1:9],"little")
    except: pass
    return 0
def work(mint):
    os_=oldest_sig(mint)
    if not os_: return (mint,None)
    tx=C.gettx(os_["signature"])
    f=C.parse_create(tx)
    if not f: return (mint,{"error":"noparse","create_sig":os_["signature"],"create_slot_hint":os_["slot"]})
    f["create_cu_price"]=create_cu(tx)
    f["create_sig"]=os_["signature"]
    return (mint,f)
res={}
with ThreadPoolExecutor(max_workers=20) as ex:
    for i,(m,f) in enumerate(ex.map(work,mints)):
        res[m]=f
        if (i+1)%40==0: print("  ",i+1,flush=True)
# attach his attempt stats
out=[]
for m in mints:
    f=res[m]
    buys=bym[m]
    rec={"mint":m,"n_buys":len(buys),"n_landed":sum(1 for b in buys if not b["failed"]),
         "n_failed":sum(1 for b in buys if b["failed"]),
         "his_buy_lamports_max":max(b["buy_lamports"] for b in buys),
         "his_cu_price_max":max(b["cu_price"] for b in buys),
         "his_first_slot":min(b["slot"] for b in buys)}
    if f and "error" not in f:
        rec.update({"create_found":True,"create_slot":f.get("create_slot"),"creator":f.get("creator"),
            "mayhem":f.get("mayhem"),"cashback":f.get("cashback"),"creator_fee_bps":f.get("creator_fee_bps"),
            "holder_reward":f.get("holder_reward"),"dev_buy":f.get("dev_buy"),"dev_buy_wire":f.get("dev_buy_wire"),
            "token_recv":f.get("token_recv"),"entry_px":f.get("entry_px"),"create_cu_price":f.get("create_cu_price"),
            "is_v2":f.get("is_v2")})
        rec["buy_delta"]=rec["his_first_slot"]-f.get("create_slot") if f.get("create_slot") else None
    else:
        rec["create_found"]=False
    out.append(rec)
json.dump(out,open("attempted_feat.json","w"),indent=0)
ok=sum(1 for r in out if r.get("create_found"))
print("enriched",len(out),"create_found",ok,flush=True)
