import requests, json, sys, time
sys.path.insert(0,"/root/nonvanilla_re")
from pda import b58d, b58e
RPC=open("/root/snipe_study50/rpc_url.txt").read().strip()
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
WALLET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
BUYDISC="e1f7501ed5b38488"
def rpc(m,p,tries=6):
    for i in range(tries):
        try:
            j=requests.post(RPC,json={"jsonrpc":"2.0","id":1,"method":m,"params":p},timeout=35).json()
            if "result" in j: return j["result"]
            time.sleep(0.35)
        except: time.sleep(0.5)
    return None
def gt(sig): return rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
def allix(tx):
    msg=tx["transaction"]["message"]; meta=tx.get("meta") or {}
    out=list(msg.get("instructions",[]))
    for inr in meta.get("innerInstructions",[]): out+=inr.get("instructions",[])
    return out
def buyaccs(tx):
    for ix in allix(tx):
        if ix.get("programId")!=PUMP: continue
        d=ix.get("data")
        if not d: continue
        try: raw=b58d(d)
        except: continue
        if raw[:8].hex()!=BUYDISC: continue
        a=ix.get("accounts",[])
        if len(a)>8 and a[8]==WALLET: return a
    return None
recs=json.load(open("/root/snipe_study50/enriched200.json"))["records"]
from collections import Counter
bb=Counter(); fc=Counter(); btp=Counter(); qtp=Counter()
n=0
for r in recs:
    tx=gt(r["sig"])
    if not tx: continue
    a=buyaccs(tx)
    if not a or len(a)<17: continue
    n+=1; bb[a[13]]+=1; fc[a[12]]+=1; btp[a[3]]+=1; qtp[a[4]]+=1
print("decoded buys:",n)
print("distinct fee_config[12]:",len(fc),dict(fc))
print("distinct base_token_program[3]:",dict(btp))
print("distinct quote_token_program[4]:",dict(qtp))
print("distinct buyback_fee_recipient[13]:",len(bb))
for k,v in bb.most_common(): print("   ",v,k)
# fee_config unaligned scan for these recipients
import base64
r=rpc("getAccountInfo",["8Wf5TiAheLUqBrKXeYg2JtAFFMWtKdG2BSFgqUcPVwTt",{"encoding":"base64"}])
data=base64.b64decode(r["value"]["data"][0])
print("fee_config len",len(data),"owner",r["value"]["owner"])
rb={k:b58d(k) for k in bb}
hits={}
for off in range(0,len(data)-31):
    ch=data[off:off+32]
    for k,v in rb.items():
        if ch==v: hits.setdefault(k,[]).append(off)
print("recipient offsets in fee_config:")
for k in bb:
    print("   ",k,hits.get(k,"NOT-FOUND"))
