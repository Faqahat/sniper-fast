import sys, json, base64, struct, threading
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
sys.path.insert(0,"/root/tmp_creator")
from analyze import rpc, bonding_curve, b58encode, CREATOR
mt=json.load(open("/root/tmp_creator/mint_trade.json"))
mints=list(mt.keys())
print("traded mints (as fp):",len(mints))
lock=threading.Lock()
buckets=Counter(); rs_vals=[]; creators=Counter(); live=0
def chk(m):
    bc=bonding_curve(m)
    ai=rpc("getAccountInfo",[bc,{"encoding":"base64","commitment":"confirmed"}])
    v=ai.get("value") if ai else None
    if not v: return (m,"no_curve",None,None)
    raw=base64.b64decode(v["data"][0]); owner=v["owner"]
    if len(raw)<81 or owner!="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P":
        return (m,"not_pump_curve",None,None)
    rs=struct.unpack_from("<Q",raw,32)[0]/1e9
    complete=raw[48]
    creator=b58encode(raw[49:81])
    return (m,"graduated" if complete else "active",rs,creator)
with ThreadPoolExecutor(max_workers=12) as ex:
    for m,st,rs,creator in ex.map(chk,mints):
        if st in("graduated","active"):
            live+=1
            if creator==CREATOR: creators["bwamJz"]+=1
            else: creators["other"]+=1
            if st=="graduated": buckets["GRADUATED"]+=1
            else:
                rs_vals.append(rs)
                if rs<2: buckets["died(<2)"]+=1
                elif rs<10: buckets["small(2-10)"]+=1
                elif rs<30: buckets["mid(10-30)"]+=1
                else: buckets["big(30-85)"]+=1
        else:
            buckets[st]+=1
print("live pump bonding-curves among traded:",live)
print("curve creator==bwamJz:",creators.get("bwamJz",0),"other:",creators.get("other",0))
print("buckets:",dict(buckets))
if rs_vals:
    rs_vals.sort()
    print(f"active-curve real_sol: n={len(rs_vals)} median={rs_vals[len(rs_vals)//2]:.2f} max={max(rs_vals):.2f} mean={sum(rs_vals)/len(rs_vals):.2f}")
