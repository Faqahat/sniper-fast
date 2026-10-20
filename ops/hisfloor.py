import json, urllib.request, os, time, sys
TOK=os.environ["CONSTANTK_TOKEN"]; RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
WALLET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
START=float(sys.argv[1]) if len(sys.argv)>1 else 0
def rpc(m,p):
    req=urllib.request.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={"content-type":"application/json"})
    for _ in range(3):
        try: return json.load(urllib.request.urlopen(req,timeout=20)).get("result")
        except: time.sleep(0.3)
    return None
# our tracked paths (every token) keyed by mint
paths={}
for ln in open("/root/sniper-fast/paths_broad.jsonl"):
    try: d=json.loads(ln)
    except: continue
    if isinstance(d,dict) and d.get("mint") and isinstance(d.get("path"),list) and d["path"] and d["path"][0][1]<2.0:
        paths[d["mint"]]=d["path"]
# his buys since START
before=None; his=set()
for _ in range(12):
    p=[WALLET,{"limit":1000}]
    if before: p[1]["before"]=before
    r=rpc("getSignaturesForAddress",p)
    if not r: break
    before=r[-1]["signature"]; stop=False
    for s in r:
        if s.get("err") or not s.get("blockTime"): continue
        if s["blockTime"]<START: stop=True; break
        tx=rpc("getTransaction",[s["signature"],{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
        if not tx or not any("Buy" in l for l in tx["meta"].get("logMessages",[])): continue
        for b in tx["meta"].get("postTokenBalances",[]):
            if b.get("mint") and b["mint"]!="So11111111111111111111111111111111111111112": his.add(b["mint"]); break
    if stop or len(r)<1000: break
FEE=0.0125; FIX=0.000365
def pnl(path, er=1.0, ride=1.15, trail=0.95, cap_ms=40000, derisk=0.30, ladder=0.25):
    peak=er; riding=False; rem=1.0; proceeds=0.0; firstclip=False; last=er; lastslot=-99
    for i,(t,r) in enumerate(path):
        if t>cap_ms: break
        if r>peak: peak=r
        if not firstclip: proceeds+=derisk*(r/er); rem-=derisk; firstclip=True
        if not riding and r/er>=ride: riding=True
        if riding and r<=peak*trail: proceeds+=rem*(r/er); rem=0; break
        if riding and i-lastslot>=4 and rem>ladder: proceeds+=ladder*(r/er); rem-=ladder; lastslot=i
        last=r
    if rem>0: proceeds+=rem*(last/er)
    return proceeds*(1-FEE)-(1+FEE)-2*FIX
matched=[pnl(paths[m]) for m in his if m in paths]
missing=len(his)-len(matched)
n=len(matched)
if n:
    v=sorted(x for x in matched if x<=18); nn=len(v); k=max(1,nn//10)
    print(f"HIS-BUYS-AT-FLOOR (his exit): his={len(his)} matched(we had path)={n} no-path={missing}")
    print(f"  mean={sum(v)/nn:+.4f} median={v[nn//2]:+.4f} win={100*sum(1 for x in v if x>0)/nn:.0f}% net={sum(v):+.2f} exT10={sum(v[:-k])/(nn-k):+.4f}")
else:
    print(f"his={len(his)} matched=0 (no overlap yet)")
