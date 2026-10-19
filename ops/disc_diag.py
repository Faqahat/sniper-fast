import os, json, urllib.request, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
RPC = "https://rpc-frankfurt.constant-k.com/?api-key=" + os.environ["CONSTANTK_TOKEN"]
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
ALPH = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n=0
    for c in s: n=n*58+ALPH.index(c)
    full=n.to_bytes((n.bit_length()+7)//8,"big") if n else b""
    return b"\x00"*(len(s)-len(s.lstrip("1")))+full
def rpc(m,p,tries=6):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode()
    for t in range(tries):
        try:
            req=urllib.request.Request(RPC,data=body,headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req,timeout=45) as r: j=json.loads(r.read())
            if "error" in j: time.sleep(0.3*(t+1)); continue
            return j.get("result")
        except Exception: time.sleep(0.4*(t+1))
    return None
def get_tx(sig):
    for v in (0,1,2):
        r=rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":v,"encoding":"jsonParsed"}])
        if r: return r
    return None
res=json.load(open("/root/creators_resolved.json"))
exp=json.load(open("/root/expanded_raw.json"))
mints=list(res["picks"].keys())
def work(mint):
    cs=exp.get(mint,{}).get("create_sig")
    if not cs: return ("NO_CS",None,None)
    tx=get_tx(cs)
    if not tx: return ("NO_TX",None,None)
    msg=tx["transaction"]["message"]
    static=[k["pubkey"] if isinstance(k,dict) else k for k in msg.get("accountKeys",[])]
    la=tx.get("meta",{}).get("loadedAddresses") or {"writable":[],"readonly":[]}
    keys=static+la.get("writable",[])+la.get("readonly",[])
    discs=[]
    ixs=list(msg.get("instructions",[]))
    inner_ct=0
    for inner in tx.get("meta",{}).get("innerInstructions",[]) or []:
        for ix in inner.get("instructions",[]): ixs.append(ix); inner_ct+=1
    toplevel_pump=[]
    for ix in msg.get("instructions",[]):
        pidx=ix.get("programIdIndex"); prog=keys[pidx] if pidx is not None and pidx<len(keys) else ix.get("programId")
        if prog==PUMP:
            try: d=b58d(ix["data"])[:8].hex()
            except: d="?"
            accs=ix.get("accounts",[])
            toplevel_pump.append((d,len(accs), type(accs[0]).__name__ if accs else "none"))
    return ("OK", tuple(toplevel_pump), None)
rows=[]
with ThreadPoolExecutor(max_workers=16) as ex:
    futs={ex.submit(work,m):m for m in mints}
    for f in as_completed(futs): rows.append(f.result())
status=Counter(r[0] for r in rows)
print("status:",dict(status))
disc_ct=Counter()
acctinfo=Counter()
for r in rows:
    if r[0]!="OK": continue
    for d,n,typ in (r[1] or []):
        disc_ct[d]+=1
        acctinfo[(d,n,typ)]+=1
print("top-level pump disc counts:",disc_ct.most_common(10))
print("disc/naccts/acctype:",acctinfo.most_common(10))
no_pump=sum(1 for r in rows if r[0]=="OK" and not r[1])
print("OK txs with NO top-level pump ix:",no_pump)
