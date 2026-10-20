import json, urllib.request, os, time, struct, base64, hashlib, threading, sys
TOK=os.environ["CONSTANTK_TOKEN"]; RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
WALLET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
PUMP_STR="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
NONVAN=["CreatorFee","creator_fee","Holder","holder_reward","Mayhem","mayhem","Cashback","cashback","Reward"]
RESULTS="/root/sniper-fast/hisbuys_results.jsonl"
LOG="/root/sniper-fast/hisbuys_paper.log"
B58="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58dec(s):
    n=0
    for c in s: n=n*58+B58.index(c)
    full=n.to_bytes((n.bit_length()+7)//8,"big"); pad=len(s)-len(s.lstrip("1"))
    return b"\x00"*pad+full
def b58enc(b):
    n=int.from_bytes(b,"big"); out=""
    while n>0: n,r=divmod(n,58); out=B58[r]+out
    pad=len(b)-len(b.lstrip(b"\x00")); return "1"*pad+out
P=2**255-1-18
def on_curve(yb):
    y=int.from_bytes(yb,"little")&((1<<255)-1)
    if y>=P: return False
    d=(-121665*pow(121666,P-2,P))%P; u=(y*y-1)%P; v=(d*y*y+1)%P
    xx=(u*pow(v,P-2,P))%P; x=pow(xx,(P+3)//8,P)
    if (x*x-xx)%P!=0: x=(x*pow(2,(P-1)//4,P))%P
    return (x*x-xx)%P==0
PUMP=b58dec(PUMP_STR)
def find_bc(mint_str):
    seeds=b"bonding-curve"+b58dec(mint_str)
    for bump in range(255,-1,-1):
        h=hashlib.sha256(seeds+bytes([bump])+PUMP+b"ProgramDerivedAddress").digest()
        if not on_curve(h): return b58enc(h)
def rpc(m,p):
    req=urllib.request.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={"content-type":"application/json"})
    for _ in range(3):
        try: return json.load(urllib.request.urlopen(req,timeout=15)).get("result")
        except: time.sleep(0.3)
    return None
def curve_vsol_vtok(bc):
    ai=rpc("getAccountInfo",[bc,{"encoding":"base64"}])
    if not ai or not ai.get("value"): return None
    raw=base64.b64decode(ai["value"]["data"][0])
    return struct.unpack_from("<Q",raw,8)[0], struct.unpack_from("<Q",raw,16)[0]
def floor_px(dev_lam): return (30e9+dev_lam)**2/(30e9*1.073e15)
FEE=0.0125; FIX=0.000365
def pnl(path, er):
    peak=er; riding=False; rem=1.0; proc=0.0; fc=False; last=er; ls=-99
    for i,(t,r) in enumerate(path):
        if r>peak: peak=r
        if not fc: proc+=0.30*(r/er); rem-=0.30; fc=True; ls=i
        if not riding and r/er>=1.15: riding=True
        if riding and r<=peak*0.95: proc+=rem*(r/er); rem=0; break
        if riding and (i-ls)>=4 and rem>0.25: proc+=0.25*(r/er); rem-=0.25; ls=i
        last=r
    if rem>0: proc+=rem*(last/er)
    return proc*(1-FEE)-(1+FEE)-2*FIX
def dev_and_vanilla(mint):
    # oldest sig = create; compute bundled dev buy = bonding-curve SOL delta in create tx - rent; vanilla from logs
    before=None; oldest=None
    for _ in range(6):
        p=[mint,{"limit":1000}];
        if before: p[1]["before"]=before
        r=rpc("getSignaturesForAddress",p)
        if not r: break
        oldest=r[-1]; before=r[-1]["signature"]
        if len(r)<1000: break
    if not oldest: return None,None
    tx=rpc("getTransaction",[oldest["signature"],{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
    if not tx: return None,None
    m=tx["meta"]; keys=[k["pubkey"] if isinstance(k,dict) else k for k in tx["transaction"]["message"]["accountKeys"]]
    dev=max((m["postBalances"][i]-m["preBalances"][i]) for i in range(len(keys)))
    dev=max(0,dev-1493520)
    van=not any(w in l for l in m.get("logMessages",[]) for w in NONVAN)
    return dev, van
def track(mint, dev, van):
    bc=find_bc(mint); fp=floor_px(dev)
    path=[]; t0=time.time()
    while time.time()-t0 < 42:
        vv=curve_vsol_vtok(bc)
        if vv and vv[0]:
            px=vv[1]/vv[0]; path.append([ (time.time()-t0)*1000.0, px/fp ])
        time.sleep(1.3)
    if len(path)<2: return
    pf=pnl(path,1.0); p11=pnl(path,1.10); peak=max(r for _,r in path)
    rec={"mint":mint,"dev":dev/1e9,"vanilla":van,"peak":round(peak,3),"pnl_floor":round(pf,4),"pnl_110":round(p11,4)}
    with open(RESULTS,"a") as f: f.write(json.dumps(rec)+"\n")
    with open(LOG,"a") as f: f.write(f"  TRADE {mint[:10]} dev={dev/1e9:.2f} peak={peak:.2f}x pnl_floor={pf:+.4f} pnl_1.10x={p11:+.4f}\n")

def summarize():
    try: recs=[json.loads(l) for l in open(RESULTS)]
    except: recs=[]
    if not recs: return "no trades yet"
    def st(key):
        v=sorted(min(r[key],18) for r in recs); n=len(v)
        return f"n={n} mean={sum(v)/n:+.4f} median={v[n//2]:+.4f} win={100*sum(1 for x in v if x>0)/n:.0f}% net={sum(v):+.2f}"
    return f"FLOOR: {st('pnl_floor')}\n1.10x: {st('pnl_110')}"

open(LOG,"a").write(f"\n=== HIS-FILTERED-BUYS PAPER started {time.strftime('%H:%M')}UTC (dev>=0.5 + vanilla, bundled; his exit ladder) ===\n")
seen=set(); start=time.time()
while True:
    sigs=rpc("getSignaturesForAddress",[WALLET,{"limit":50}]) or []
    for s in sigs:
        if s.get("err") or not s.get("blockTime") or s["blockTime"]<start: continue
        if s["signature"] in seen: continue
        seen.add(s["signature"])
        tx=rpc("getTransaction",[s["signature"],{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
        if not tx or not any("Buy" in l for l in tx["meta"].get("logMessages",[])): continue
        mint=None
        for b in tx["meta"].get("postTokenBalances",[]):
            if b.get("mint") and b["mint"]!="So11111111111111111111111111111111111111112": mint=b["mint"]; break
        if not mint: continue
        dev,van=dev_and_vanilla(mint)
        if dev is None: continue
        passed = dev>=500000000 and dev<=8000000000 and van
        open(LOG,"a").write(f"HIS BUY {mint[:10]} dev={dev/1e9:.2f} van={van} -> {'TRADE (passes filter)' if passed else 'skip (filter)'}\n")
        if passed:
            threading.Thread(target=track,args=(mint,dev,van),daemon=True).start()
    time.sleep(4)
