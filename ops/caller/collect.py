import requests, json, sys, time
from concurrent.futures import ThreadPoolExecutor

RPC = open("/root/snipe_study50/rpc_url.txt").read().strip()
TARGET = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
BUY_DISC = "e1f7501ed5b38488"

_A="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n=0
    for c in s: n=n*58+_A.index(c)
    full=n.to_bytes((n.bit_length()+7)//8,'big')
    pad=len(s)-len(s.lstrip('1'))
    return b'\x00'*pad+full

picks = json.load(open("/root/last500/his_500.json"))
# map mint -> anchor create_slot and his_buy_slot
his_mints = {}
for p in picks:
    cs = p.get("create_slot") or p.get("create_slot_pre")
    if cs is None: continue
    his_mints[p["mint"]] = {"create_slot": cs, "his_buy_slot": p.get("his_buy_slot")}

WIN = 3
# union of slots needed
slots = set()
for m,info in his_mints.items():
    for d in range(0, WIN+1):
        slots.add(info["create_slot"]+d)
slots = sorted(slots)
print(f"mints={len(his_mints)} slots_to_fetch={len(slots)}", file=sys.stderr)

sess = requests.Session()
def getblock(slot, tries=4):
    for i in range(tries):
        try:
            r=sess.post(RPC,json={"jsonrpc":"2.0","id":1,"method":"getBlock","params":[slot,{"maxSupportedTransactionVersion":1,"transactionDetails":"full","rewards":False,"encoding":"json"}]},timeout=90)
            j=r.json()
            if "result" in j: return j["result"]
            e=j.get("error",{})
            if e.get("code")==-32007 or "skipped" in str(e).lower(): return None  # skipped slot
            time.sleep(0.5)
        except Exception:
            time.sleep(0.6)
    return None

def parse_block(slot, res):
    """return list of (mint, slot, txindex, buyer, lamports) for pump buys of his mints"""
    out=[]
    if not res: return out
    txs=res.get("transactions",[])
    for ti,tx in enumerate(txs):
        meta=tx.get("meta") or {}
        if meta.get("err") is not None: continue
        msg=tx["transaction"]["message"]
        keys=list(msg.get("accountKeys",[]))
        la=meta.get("loadedAddresses") or {}
        keys = keys + list(la.get("writable",[])) + list(la.get("readonly",[]))
        # gather instructions top+inner
        allix=list(msg.get("instructions",[]))
        for inner in meta.get("innerInstructions",[]):
            allix.extend(inner.get("instructions",[]))
        for ix in allix:
            pidx=ix.get("programIdIndex")
            if pidx is None or pidx>=len(keys): continue
            if keys[pidx]!=PUMP: continue
            data=ix.get("data")
            if not data: continue
            try: raw=b58d(data)
            except: continue
            if raw[:8].hex()!=BUY_DISC: continue
            accs=ix.get("accounts",[])
            if len(accs)<17: continue
            try:
                mint=keys[accs[1]]; buyer=keys[accs[8]]
            except: continue
            if mint not in his_mints: continue
            try: lam=int.from_bytes(raw[8:16],'little')
            except: lam=None
            out.append((mint,slot,ti,buyer,lam))
    return out

records=[]
done=0
def work(slot):
    res=getblock(slot)
    return parse_block(slot,res)

with ThreadPoolExecutor(max_workers=24) as ex:
    for recs in ex.map(work, slots):
        records.extend(recs)
        done+=1
        if done%200==0: print(f"  {done}/{len(slots)} slots, {len(records)} buys",file=sys.stderr)

print(f"total buy records: {len(records)}", file=sys.stderr)
json.dump({"target":TARGET,"win":WIN,"records":records,"his_mints":his_mints},
          open("/root/caller/buys_raw.json","w"))
print("wrote buys_raw.json", file=sys.stderr)
