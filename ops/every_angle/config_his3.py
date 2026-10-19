import json, sys, threading
import concurrent.futures as cf
sys.path.insert(0,'/root/last30')
import rpc
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
CV2="d6904cec5f8b31b4"; CV1="181ec828051c0777"
_A="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n=0
    for c in s: n=n*58+_A.index(c)
    o=bytearray()
    while n>0: o.append(n&0xff); n>>=8
    o.reverse(); return bytes(len(s)-len(s.lstrip('1')))+bytes(o)
def cfg_from_data(dd):
    disc=dd[:8].hex()
    if disc==CV1: return dict(is_v2=False,mayhem=0,cashback=0,creator_fee_bps=0,holder_reward=0)
    if disc!=CV2: return None
    q=8
    try:
        for _ in range(3):
            ln=int.from_bytes(dd[q:q+4],'little'); q+=4+ln
        q+=32
        return dict(is_v2=True,mayhem=dd[q],cashback=dd[q+1],
                    creator_fee_bps=int.from_bytes(dd[q+2:q+10],'little'),holder_reward=dd[q+10])
    except Exception:
        return dict(is_v2=True,parse_err=True)
def get_cfg(slot, mint):
    b=rpc.call("getBlock",[slot,{"encoding":"json","transactionDetails":"full","maxSupportedTransactionVersion":1,"rewards":False}])
    if not b: return None
    for tx in b["transactions"]:
        msg=tx["transaction"]["message"]; keys=msg["accountKeys"]; meta=tx.get("meta") or {}
        la=meta.get("loadedAddresses",{}) or {}
        allk=keys+la.get("writable",[])+la.get("readonly",[])
        if PUMP not in allk or mint not in allk: continue
        allins=list(msg["instructions"])
        for inner in meta.get("innerInstructions",[]): allins+=inner.get("instructions",[])
        for ins in allins:
            if allk[ins["programIdIndex"]]!=PUMP: continue
            try: dd=b58d(ins["data"])
            except: continue
            if dd[:8].hex() in (CV1,CV2):
                c=cfg_from_data(dd)
                if c: return c
    return None
tape=[d for d in json.load(open('/root/mirror/his_tape.json')) if d.get('create_slot')]
out={}; lock=threading.Lock(); done=[0]
def work(d):
    try: c=get_cfg(d['create_slot'], d['mint'])
    except Exception as e: c={"error":str(e)[:40]}
    with lock:
        done[0]+=1
        if done[0]%40==0: print(f"  {done[0]}/{len(tape)}",file=sys.stderr)
    return d['mint'], c
with cf.ThreadPoolExecutor(max_workers=8) as ex:
    for m,c in ex.map(work,tape): out[m]=c
json.dump(out,open('/root/every_angle/his_config.json','w'))
print(f"parsed {sum(1 for v in out.values() if v and 'mayhem' in v)}/{len(tape)}",file=sys.stderr)
