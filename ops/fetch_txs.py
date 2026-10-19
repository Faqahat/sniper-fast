import json, urllib.request, os, time, random
from concurrent.futures import ThreadPoolExecutor
RPC = "https://rpc-frankfurt.constant-k.com/?api-key=" + os.environ["CONSTANTK_TOKEN"]
WALLET = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
def rpc(method, params):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    for attempt in range(8):
        try:
            req = urllib.request.Request(RPC, data=body, headers={"Content-Type":"application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=40).read())["result"]
        except Exception as e:
            time.sleep(min(8, 0.5*(2**attempt)) + random.random())
    return None

sigs=json.load(open("/root/wallet_sigs.json"))
good=[s for s in sigs if not s["err"]]
sigmeta={s["sig"]:s for s in good}

def parse(sig):
    tx=rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
    if tx is None: return sig, None
    meta=tx["meta"]
    msg=tx["transaction"]["message"]
    accts=[a["pubkey"] for a in msg["accountKeys"]]
    # loaded addresses
    la=meta.get("loadedAddresses") or {}
    accts = accts + la.get("writable",[]) + la.get("readonly",[])
    # wallet index for lamports
    try: widx=accts.index(WALLET)
    except ValueError: widx=None
    lamport_delta=None
    if widx is not None and widx < len(meta["preBalances"]):
        lamport_delta = meta["postBalances"][widx]-meta["preBalances"][widx]
    # token deltas for wallet owner, per mint
    pre={}; post={}
    for b in meta.get("preTokenBalances",[]):
        if b.get("owner")==WALLET:
            pre[b["mint"]]=int(b["uiTokenAmount"]["amount"])
    for b in meta.get("postTokenBalances",[]):
        if b.get("owner")==WALLET:
            post[b["mint"]]=int(b["uiTokenAmount"]["amount"])
    mints=set(pre)|set(post)
    tokdeltas={m:post.get(m,0)-pre.get(m,0) for m in mints}
    logs=meta.get("logMessages",[])
    instrs=[l.split("Instruction: ")[1] for l in logs if "Instruction: " in l]
    return sig, {"fee":meta["fee"],"lamport_delta":lamport_delta,"tokdeltas":tokdeltas,"instrs":instrs}

out={}
siglist=[s["sig"] for s in good]
done=0
with ThreadPoolExecutor(12) as ex:
    for sig,res in ex.map(parse, siglist):
        out[sig]=res
        done+=1
        if done%300==0: print("parsed",done)
# attach slot/blocktime
for sig,res in out.items():
    if res is not None:
        res["slot"]=sigmeta[sig]["slot"]; res["blockTime"]=sigmeta[sig]["blockTime"]
json.dump(out, open("/root/parsed_txs.json","w"))
fails=sum(1 for v in out.values() if v is None)
print("DONE parsed", len(out), "fails", fails)
