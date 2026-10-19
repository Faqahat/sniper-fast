import json, sys, threading
import concurrent.futures as cf
sys.path.insert(0,'/root/profit_backtest')
import common as C
CREATE_V2="d6904cec5f8b31b4"; CREATE="181ec828051c0777"
tape=json.load(open('/root/mirror/his_tape.json'))
mints=[d['mint'] for d in tape]
def all_ix_data(tx):
    msg=tx['transaction']['message']; out=[]
    for ix in msg.get('instructions',[]):
        if ix.get('programId')==C.PUMP_B58 and ix.get('data'): out.append(ix['data'])
    for inner in (tx.get('meta',{}) or {}).get('innerInstructions',[]) or []:
        for ix in inner.get('instructions',[]):
            if ix.get('programId')==C.PUMP_B58 and ix.get('data'): out.append(ix['data'])
    return out
def parse_cfg(tx):
    for data in all_ix_data(tx):
        try: dd=C.b58dec(data)
        except: continue
        disc=dd[:8].hex()
        if disc==CREATE_V2:
            q=8
            try:
                for _ in range(3):
                    ln=int.from_bytes(dd[q:q+4],'little'); q+=4+ln
                q+=32
                return dict(is_v2=True, mayhem=dd[q], cashback=dd[q+1],
                            creator_fee_bps=int.from_bytes(dd[q+2:q+10],'little'), holder_reward=dd[q+10])
            except Exception: return dict(is_v2=True, parse_err=True)
        if disc==CREATE:
            return dict(is_v2=False, mayhem=0, cashback=0, creator_fee_bps=0, holder_reward=0)
    return None
def oldest_sig(mint):
    out=[]; before=None
    for _ in range(15):
        o={"limit":1000}
        if before: o["before"]=before
        pg=C.rpc("getSignaturesForAddress",[mint,o])
        if not pg: break
        out+=pg
        if len(pg)<1000: break
        before=pg[-1]["signature"]
    if not out: return None
    out.sort(key=lambda s:(s.get("slot") or 0))
    return out[0]["signature"]
out={}; lock=threading.Lock(); done=[0]
def work(mint):
    rec=None
    try:
        sig=oldest_sig(mint)
        if sig:
            tx=C.gettx(sig)
            if tx: rec=parse_cfg(tx)
    except Exception as e: rec={"error":str(e)[:50]}
    with lock:
        done[0]+=1
        if done[0]%25==0: print(f"  {done[0]}/{len(mints)}",file=sys.stderr)
    return mint,rec
with cf.ThreadPoolExecutor(max_workers=10) as ex:
    for m,r in ex.map(work,mints): out[m]=r
json.dump(out,open('/root/every_angle/his_config.json','w'))
got=sum(1 for v in out.values() if v and 'mayhem' in v)
print(f"done parsed {got}/{len(mints)}",file=sys.stderr)
