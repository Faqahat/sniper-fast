import json, urllib.request, os, time, random, base64, struct
from concurrent.futures import ThreadPoolExecutor
RPC = "https://rpc-frankfurt.constant-k.com/?api-key=" + os.environ["CONSTANTK_TOKEN"]
WALLET = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"

def rpc(method, params):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    for a in range(8):
        try:
            req=urllib.request.Request(RPC,data=body,headers={"Content-Type":"application/json"})
            return json.loads(urllib.request.urlopen(req,timeout=40).read())["result"]
        except Exception: time.sleep(min(8,0.5*2**a)+random.random())
    return None

parsed=json.load(open("/root/parsed_txs.json"))
rt=json.load(open("/root/roundtrips.json"))["roundtrips"]

# map mint -> list of (sig) that touch it with nonzero delta, from parsed
from collections import defaultdict
mint_sigs=defaultdict(set)
for sig,v in parsed.items():
    if v is None: continue
    for m,td in v["tokdeltas"].items():
        if td!=0: mint_sigs[m].add(sig)

# we want all 514 mints' sigs so we can decode prices everywhere
want_mints=set(r["mint"] for r in rt)
want_sigs=set()
for m in want_mints: want_sigs|=mint_sigs[m]
print("sigs to fetch:", len(want_sigs))

_B58="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58decode(s):
    n=0
    for ch in s: n=n*58+_B58.index(ch)
    full=n.to_bytes((n.bit_length()+7)//8,"big")
    pad=len(s)-len(s.lstrip("1"))
    return b"\x00"*pad+full
WALLET_BYTES=b58decode(WALLET)

def decode_trade_events(logs):
    # returns list of dicts for pump TradeEvent where user==WALLET
    out=[]
    for l in logs:
        if "Program data:" not in l: continue
        b64=l.split("Program data:")[1].strip()
        try: raw=base64.b64decode(b64)
        except Exception: continue
        # TradeEvent: 8 disc + mint32 + solAmount u64 + tokenAmount u64 + isBuy u8 + user32 + ts i64 + vsol u64 + vtok u64 ...
        if len(raw) < 8+32+8+8+1+32+8+8+8: continue
        off=8
        mint=raw[off:off+32]; off+=32
        sol_amount=struct.unpack_from("<Q",raw,off)[0]; off+=8
        token_amount=struct.unpack_from("<Q",raw,off)[0]; off+=8
        is_buy=raw[off]; off+=1
        user=raw[off:off+32]; off+=32
        ts=struct.unpack_from("<q",raw,off)[0]; off+=8
        vsol=struct.unpack_from("<Q",raw,off)[0]; off+=8
        vtok=struct.unpack_from("<Q",raw,off)[0]; off+=8
        out.append({"mint32":mint,"sol_amount":sol_amount,"token_amount":token_amount,
                    "is_buy":bool(is_buy),"user32":user,"vsol":vsol,"vtok":vtok})
    return out

def fetch(sig):
    tx=rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
    if tx is None: return sig,None
    meta=tx["meta"]; logs=meta.get("logMessages",[])
    evs=[e for e in decode_trade_events(logs) if e["user32"]==WALLET_BYTES]
    return sig,{"slot":tx["slot"],"bt":tx["blockTime"],"events":evs}

res={}
sl=list(want_sigs); done=0
with ThreadPoolExecutor(12) as ex:
    for sig,v in ex.map(fetch, sl):
        res[sig]=v; done+=1
        if done%300==0: print("fetched",done)
# store raw (bytes->b64)
import base64 as b64m
ser={}
for sig,v in res.items():
    if v is None: ser[sig]=None; continue
    evs=[]
    for e in v["events"]:
        evs.append({"mint":b64m.b64encode(e["mint32"]).decode(),"sol":e["sol_amount"],"tok":e["token_amount"],
                    "is_buy":e["is_buy"],"user":b64m.b64encode(e["user32"]).decode(),"vsol":e["vsol"],"vtok":e["vtok"]})
    ser[sig]={"slot":v["slot"],"bt":v["bt"],"events":evs}
json.dump(ser, open("/root/leg_events.json","w"))
print("DONE fetched", len(res), "fails", sum(1 for v in res.values() if v is None))
