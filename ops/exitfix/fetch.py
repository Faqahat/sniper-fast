import json,urllib.request,hashlib,os,concurrent.futures as cf,time
TOK=os.environ["CONSTANTK_TOKEN"]
RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
B58="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58dec(s):
    n=0
    for c in s: n=n*58+B58.index(c)
    f=n.to_bytes((n.bit_length()+7)//8,"big"); return b"\x00"*(len(s)-len(s.lstrip("1")))+f
def b58enc(b):
    n=int.from_bytes(b,"big"); o=""
    while n>0: n,r=divmod(n,58); o=B58[r]+o
    return "1"*(len(b)-len(b.lstrip(b"\x00")))+o
P=2**255-19
def oc(yb):
    y=int.from_bytes(yb,"little")&((1<<255)-1)
    if y>=P: return False
    d=(-121665*pow(121666,P-2,P))%P;u=(y*y-1)%P;v=(d*y*y+1)%P;xx=(u*pow(v,P-2,P))%P;x=pow(xx,(P+3)//8,P)
    if (x*x-xx)%P!=0:x=(x*pow(2,(P-1)//4,P))%P
    return (x*x-xx)%P==0
PUMP=b58dec("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
def bc(m):
    s=b"bonding-curve"+b58dec(m)
    for b in range(255,-1,-1):
        h=hashlib.sha256(s+bytes([b])+PUMP+b"ProgramDerivedAddress").digest()
        if not oc(h): return b58enc(h)
def rpc(m,p):
    req=urllib.request.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={"content-type":"application/json"})
    for i in range(6):
        try: return json.load(urllib.request.urlopen(req,timeout=25)).get("result")
        except: time.sleep(0.4*(i+1))
    return None
def sigs_all(cv,cap=4000):
    out=[];before=None
    while True:
        prm=[cv,{"limit":1000}] if before is None else [cv,{"limit":1000,"before":before}]
        r=None
        for _ in range(5):
            r=rpc("getSignaturesForAddress",prm)
            if r is not None: break
            time.sleep(0.6)
        if not r: break
        out+=r
        if len(r)<1000: break
        before=r[-1]["signature"]
        if len(out)>cap: break
    return out
def tx_point(sig,cv):
    tx=rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
    if not tx: return None
    try:
        keys=[k["pubkey"] for k in tx["transaction"]["message"]["accountKeys"]]
        if cv in keys:
            i=keys.index(cv)
            return (tx.get("slot",0), tx.get("blockTime",0), tx["meta"]["postBalances"][i])
    except: return None
    return None

# mint -> dev_buy lamports
TRADES={
 "2pQgSF6QZ9zfxDDEvbKHauUbk6Sh5nZs2KV4CMfqpump":1000000000,
 "GzYCJrGDJzBj5Um8xzTqNPE5ViR9x5XJXmjW7Qrapump":3000000000,
 "DT3XpNHrMNXFp21DZj6PrcZG6HFopiLEdWTV3odPpump":4940000000,
 "3vYr2zKAoSjHtpC5WXTEwKiWyJpTBpBcsSXwg4Pppump":1000000000,
 "3jh3EVr6FMdCX5xxQq9rh9HXYHhRoayCVZFeHtoTpump":1000000000,
 "CsSqMZxjR4Z8n9VxTV3shmptSekqaiwp2ySrSJaFR9jn":2000000000,
 "6Txr19fyrDJ5TH1ph9NB8QtCafLrcGYd6waUJLdqpump":1000000000,
 "FV7Z7H7QaR4ZgfCWe3mKoZgEkoLEkdFmTCzy5jy6pump":1000000000,
 "JE9LHzWe2ovReNuxPBfxvfAci18gr54nRpcsGLG6pump":1000000000,
}
CACHE="/root/exitfix/series_cache.json"
cache=json.load(open(CACHE)) if os.path.exists(CACHE) else {}
for mint in TRADES:
    if mint in cache and len(cache[mint])>2:
        print(f"skip {mint[:10]} cached n={len(cache[mint])}",flush=True); continue
    cv=bc(mint)
    sg=[x["signature"] for x in sigs_all(cv)]
    print(f"{mint[:10]} curve={cv[:10]} nsigs={len(sg)} fetching...",flush=True)
    pts=[]
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for v in ex.map(lambda s: tx_point(s,cv), sg):
            if v and v[1]: pts.append(v)
    cache[mint]=pts
    json.dump(cache,open(CACHE,"w"))
    print(f"  cached {mint[:10]} npts={len(pts)}",flush=True)
print("FETCH_DONE",flush=True)
