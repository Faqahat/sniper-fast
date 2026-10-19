import json, urllib.request, os, time, re, subprocess
TOK=os.environ["CONSTANTK_TOKEN"]; RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
WALLET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
def rpc(m,p):
    req=urllib.request.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={"content-type":"application/json"})
    for _ in range(3):
        try: return json.load(urllib.request.urlopen(req,timeout=20)).get("result")
        except: time.sleep(0.3)
    return None
# paper run start epoch = now - engine etimes
try:
    et=int(subprocess.check_output(["bash","-c","ps -eo etimes,args | grep -E '\\./target/release/snipe_engine --paper-trade' | grep -v grep | grep -v timeout | awk '{print $1}' | head -1"]).split()[0])
except: et=0
start=time.time()-et
print(f"paper run started {et}s ago (epoch {int(start)})")
# our paper tracked mints
tracked=set()
try:
    for ln in open("/root/arbx-fast/paper_filter8h.log"):
        mo=re.search(r"PAPER launch #\d+ slot=\d+ mint=([1-9A-HJ-NP-Za-km-z]+)",ln)
        if mo: tracked.add(mo.group(1))
except: pass
print(f"our paper tracked {len(tracked)} launches since start")
# his buys since paper start
sigs=rpc("getSignaturesForAddress",[WALLET,{"limit":200}]) or []
his_buys=[]  # (mint, slot, blockTime)
for s in sigs:
    if s.get("err") or not s.get("blockTime") or s["blockTime"]<start: continue
    tx=rpc("getTransaction",[s["signature"],{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
    if not tx: continue
    logs=tx["meta"].get("logMessages",[])
    if not any("Buy" in l for l in logs): continue
    # mint = the non-WSOL token in postTokenBalances owned by wallet
    mint=None
    for b in tx["meta"].get("postTokenBalances",[]):
        if b.get("mint") and b["mint"]!="So11111111111111111111111111111111111111112": mint=b["mint"]; break
    if mint: his_buys.append((mint, s["slot"], s["blockTime"]))
print(f"\n4yFAz made {len(his_buys)} buys since our paper started:")
caught=0; missed=[]
for mint,slot,bt in his_buys:
    hit = mint in tracked
    if hit: caught+=1
    else: missed.append((mint,slot))
    print(f"  {'CAUGHT ' if hit else 'MISSED '} {mint[:12]}.. slot={slot} time={time.strftime('%H:%M:%S',time.gmtime(bt))}")
print(f"\nSUMMARY: his buys={len(his_buys)}  WE CAUGHT={caught}  MISSED={len(missed)}")
