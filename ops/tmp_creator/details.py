import sys, json, base64, struct
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,"/root/tmp_creator")
from analyze import rpc, bonding_curve, b58encode, CREATOR
mt=json.load(open("/root/tmp_creator/mint_trade.json"))
mints=list(mt.keys())
def chk(m):
    bc=bonding_curve(m)
    ai=rpc("getAccountInfo",[bc,{"encoding":"base64","commitment":"confirmed"}])
    v=ai.get("value") if ai else None
    if not v: return (m,"no_curve",None,None,mt[m])
    raw=base64.b64decode(v["data"][0]); owner=v["owner"]
    if len(raw)<81 or owner!="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P":
        return (m,"not_pump",None,None,mt[m])
    rs=struct.unpack_from("<Q",raw,32)[0]/1e9
    return (m,"grad" if raw[48] else "active",rs,b58encode(raw[49:81]),mt[m])
res=list(ThreadPoolExecutor(max_workers=12).map(chk,mints))
print("=== mints CREATED by bwamJz (curve creator==bwamJz) ===")
for m,st,rs,cr,tc in res:
    if cr==CREATOR: print(f"  {m} status={st} real_sol={rs} tradecount={tc}")
print("=== graduated tokens it traded ===")
for m,st,rs,cr,tc in res:
    if st=="grad": print(f"  {m} creator={cr[:8]} tradecount={tc}")
print("=== biggest active runners (real_sol>=2) ===")
for m,st,rs,cr,tc in sorted([r for r in res if r[1]=='active' and r[2]>=2],key=lambda x:-x[2]):
    print(f"  {m} real_sol={rs:.2f} creator={cr[:8]} tradecount={tc}")
