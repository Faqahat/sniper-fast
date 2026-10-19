import json, sys, threading
import concurrent.futures as cf
sys.path.insert(0,'/root/profit_backtest')
import common as C

tape=json.load(open('/root/mirror/his_tape.json'))
mints=[d['mint'] for d in tape]
print(f"fetching create config for {len(mints)} his picks", file=sys.stderr)

def oldest_create_sig(mint):
    # paginate to oldest signatures of the mint
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
    try:
        sig=oldest_create_sig(mint)
        rec=None
        if sig:
            tx=C.gettx(sig)
            pc=C.parse_create(tx)
            if pc:
                rec={k:pc.get(k) for k in ('is_v2','mayhem','cashback','creator','entry_px')}
                # parse_create returns feebps/holder as part of dict? re-extract
                rec['creator_fee_bps']=pc.get('creator_fee_bps')
                rec['holder_reward']=pc.get('holder_reward')
                rec['mayhem']=pc.get('mayhem'); rec['cashback']=pc.get('cashback')
    except Exception as e:
        rec={"error":str(e)}
    with lock:
        done[0]+=1
        if done[0]%25==0: print(f"  {done[0]}/{len(mints)}",file=sys.stderr)
    return mint, rec
with cf.ThreadPoolExecutor(max_workers=8) as ex:
    for m,r in ex.map(work, mints):
        out[m]=r
json.dump(out, open('/root/every_angle/his_config.json','w'))
got=sum(1 for v in out.values() if v and 'mayhem' in v)
print(f"done. parsed config for {got}/{len(mints)}", file=sys.stderr)
