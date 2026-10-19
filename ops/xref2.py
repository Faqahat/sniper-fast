import json, urllib.request, os, time, re, subprocess
TOK=os.environ["CONSTANTK_TOKEN"]; RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
WALLET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
def rpc(m,p):
    req=urllib.request.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={"content-type":"application/json"})
    for _ in range(3):
        try: return json.load(urllib.request.urlopen(req,timeout=20)).get("result")
        except: time.sleep(0.3)
    return None
try: et=int(subprocess.check_output(["bash","-c","ps -eo etimes,args | grep -E '\\./target/release/snipe_engine --paper-trade' | grep -v grep | grep -v timeout | awk '{print $1}' | head -1"]).split()[0])
except: et=0
start=time.time()-et; eff_start=start+150
tracked=set()
for ln in open("/root/arbx-fast/paper_broad.log"):
    mo=re.search(r"mint=([1-9A-HJ-NP-Za-km-z]+)",ln)
    if mo: tracked.add(mo.group(1))
before=None; buys=[]
for _ in range(10):
    p=[WALLET,{"limit":1000}];
    if before: p[1]["before"]=before
    r=rpc("getSignaturesForAddress",p)
    if not r: break
    before=r[-1]["signature"]; stop=False
    for s in r:
        if s.get("err") or not s.get("blockTime"): continue
        if s["blockTime"]<eff_start: stop=True; break
        buys.append(s["signature"])
    if stop or len(r)<1000: break
def dev_vanilla(mint):
    b=None; r=rpc("getSignaturesForAddress",[mint,{"limit":1000}])
    if not r: return None,None
    o=r[-1]
    for _ in range(6):
        if len(r)<1000: break
        r=rpc("getSignaturesForAddress",[mint,{"limit":1000,"before":o["signature"]}])
        if not r: break
        o=r[-1]
    tx=rpc("getTransaction",[o["signature"],{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
    if not tx: return None,None
    m=tx["meta"]; keys=[k["pubkey"] if isinstance(k,dict) else k for k in tx["transaction"]["message"]["accountKeys"]]
    dev=max(m["postBalances"][i]-m["preBalances"][i] for i in range(len(keys)))/1e9
    van=not any(w in l for l in m.get("logMessages",[]) for w in ["CreatorFee","Holder","Mayhem","Cashback","Reward"])
    return dev,van
caught=0; feed_miss=0; filt_miss=0
for sg in buys:
    tx=rpc("getTransaction",[sg,{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
    if not tx or not any("Buy" in l for l in tx["meta"].get("logMessages",[])): continue
    mint=None
    for b in tx["meta"].get("postTokenBalances",[]):
        if b.get("mint") and b["mint"]!="So11111111111111111111111111111111111111112": mint=b["mint"]; break
    if not mint: continue
    if mint in tracked: caught+=1
    else:
        dev,van=dev_vanilla(mint)
        if dev is not None and 0.5<=dev<=8 and van: feed_miss+=1
        else: filt_miss+=1
tot=caught+feed_miss+filt_miss
print(f"[{time.strftime('%H:%M',time.gmtime())}UTC run={int(et/60)}min] his buys={tot} CAUGHT={caught} FEED-MISS={feed_miss}(would pass,feed gap) FILTER-MISS={filt_miss}(dev<0.5/nonvanilla,by design) catch-of-eligible%={100*caught/(caught+feed_miss) if (caught+feed_miss) else 0:.0f}")
