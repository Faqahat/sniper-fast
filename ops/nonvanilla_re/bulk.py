import requests, json, sys, time
sys.path.insert(0,"/root/nonvanilla_re")
from pda import find_pda, b58d, b58e
RPC=open("/root/snipe_study50/rpc_url.txt").read().strip()
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
WALLET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
BUYDISC="e1f7501ed5b38488"
CREATEDISC="d6904cec5f8b31b4"
def rpc(m,p,tries=6):
    for i in range(tries):
        try:
            j=requests.post(RPC,json={"jsonrpc":"2.0","id":1,"method":m,"params":p},timeout=35).json()
            if "result" in j: return j["result"]
            time.sleep(0.4)
        except: time.sleep(0.5)
    return None
def gt(sig,ver=0): return rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":ver,"encoding":"jsonParsed"}])
def allix(tx):
    msg=tx["transaction"]["message"]; meta=tx.get("meta") or {}
    out=list(msg.get("instructions",[]))
    for inr in meta.get("innerInstructions",[]): out+=inr.get("instructions",[])
    return out
def allkeys(tx):
    msg=tx["transaction"]["message"]; meta=tx.get("meta") or {}
    keys=[a["pubkey"] for a in msg["accountKeys"]]
    la=meta.get("loadedAddresses") or {}
    keys+=la.get("writable",[])+la.get("readonly",[])
    return keys
def find_buy(tx):
    for ix in allix(tx):
        if ix.get("programId")!=PUMP: continue
        d=ix.get("data")
        if not d: continue
        try: raw=b58d(d)
        except: continue
        if raw[:8].hex()!=BUYDISC: continue
        accs=ix.get("accounts",[])
        if len(accs)>8 and accs[8]==WALLET: return raw,accs
    return None,None

def cls(h):
    if h is None: return "UNDECODED"
    b=bytes.fromhex(h); m=b[0] if b else 0; ca=b[1] if len(b)>1 else 0
    cf=int.from_bytes(b[2:10],"little") if len(b)>=10 else 0; hr=b[10] if len(b)>10 else 0
    t=[]
    if m: t.append("MAYHEM")
    if ca: t.append("CASHBACK")
    if cf: t.append("CREATORFEE")
    if hr: t.append("HOLDERREWARD")
    return "+".join(t) if t else "ODD:"+h

recs=json.load(open("/root/snipe_study50/enriched200.json"))["records"]
nv=[r for r in recs if r.get("vanilla")==False]
from collections import Counter
nacc=Counter(); dlen=Counter(); perkind=Counter(); fail=[]
in_create=Counter()
for r in nv:
    tx=gt(r["sig"])
    if not tx: fail.append((r["mint"],"NOTX")); continue
    raw,accs=find_buy(tx)
    if raw is None: fail.append((r["mint"],"NOBUY")); continue
    k=cls(r["flags_hex"])
    nacc[len(accs)]+=1; dlen[len(raw)]+=1; perkind[(k,len(accs),len(raw))]+=1
json.dump({"nacc":nacc,"dlen":dlen},open("/root/nonvanilla_re/bulk_out.json","w"))
print("NON-VANILLA buys decoded:",sum(nacc.values()),"of",len(nv))
print("account-count distribution:",dict(nacc))
print("data-length distribution:",dict(dlen))
print("per (kind,n_acc,data_len):")
for k,v in sorted(perkind.items()): print("  ",v,k)
print("failures:",fail)
