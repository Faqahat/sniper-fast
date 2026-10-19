import sys, time, json
sys.path.insert(0, "/root/indep")
from common import rpc, events, MINT_AUTH
from concurrent.futures import ThreadPoolExecutor
t=time.time(); s=rpc("getSlot",[{"commitment":"confirmed"}]); print("slot",s, time.time()-t)
bt=rpc("getBlockTime",[s-100]); print("bt",bt, time.time())
fs=rpc("getFirstAvailableBlock",[]); print("first",fs, rpc("getBlockTime",[fs]))
t=time.time(); r=rpc("getSignaturesForAddress",[MINT_AUTH,{"limit":1000}]); print("sigs",len(r), time.time()-t, r[0]["slot"], r[-1]["slot"], r[0].get("blockTime"), r[-1].get("blockTime"))
sigs=[x["signature"] for x in r[:64]]
def g(sg):
    t=time.time(); x=rpc("getTransaction",[sg,{"encoding":"json","maxSupportedTransactionVersion":1,"commitment":"confirmed"}]); return time.time()-t, x
t=time.time()
with ThreadPoolExecutor(8) as ex: res=list(ex.map(g,sigs))
print("64 tx with 8 workers", time.time()-t, sorted(a for a,_ in res)[::8])
t=time.time()
with ThreadPoolExecutor(16) as ex: res=list(ex.map(g,[x["signature"] for x in r[64:192]]))
print("128 tx with 16 workers", time.time()-t)
x=res[0][1]
tr,cr=events(x["meta"]["logMessages"]); print(cr, tr[:2])
# raw trade event length
import base64
for l in x["meta"]["logMessages"]:
    if l.startswith("Program data: "):
        raw=base64.b64decode(l[14:]+"==="); print(len(raw), raw[:8].hex())
