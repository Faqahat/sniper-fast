import json,urllib.request,os,time,statistics,concurrent.futures as cf
from collections import defaultdict
TOK=os.environ["CONSTANTK_TOKEN"]
RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
W="CUQqcZZGr8QLjEzMpxUZyiZirBujE2Y9yZDyfCRw1CAB"
SKIP={"So11111111111111111111111111111111111111112","EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v","Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"}
def rpc(m,p):
    req=urllib.request.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={"content-type":"application/json"})
    for i in range(5):
        try: return json.load(urllib.request.urlopen(req,timeout=25)).get("result")
        except: time.sleep(0.4*(i+1))
    return None
sigs=[];before=None
while True:
    prm=[W,{"limit":1000}] if before is None else [W,{"limit":1000,"before":before}]
    r=rpc("getSignaturesForAddress",prm)
    if not r: break
    sigs+=r
    if len(r)<1000: break
    before=r[-1]["signature"]
    if len(sigs)>12000: break
print("total sigs:",len(sigs))
def parse(sig):
    tx=rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
    if not tx or not tx.get("meta") or tx["meta"].get("err"): return None
    meta=tx["meta"]; keys=[k["pubkey"] for k in tx["transaction"]["message"]["accountKeys"]]
    if W not in keys: return None
    wi=keys.index(W); sol_d=(meta["postBalances"][wi]-meta["preBalances"][wi])/1e9
    # any non-WSOL/stable mint present
    mints=set()
    for b in meta.get("preTokenBalances",[])+meta.get("postTokenBalances",[]):
        if b["mint"] not in SKIP: mints.add(b["mint"])
    if not mints: return None
    mint=sorted(mints)[0] if len(mints)==1 else None
    if mint is None:
        # pick the mint whose W-owned balance changed, else the first
        mint=sorted(mints)[0]
    return (tx.get("blockTime"),sol_d,mint)
rows=[]
with cf.ThreadPoolExecutor(max_workers=8) as ex:
    for v in ex.map(lambda s: parse(s["signature"]), sigs):
        if v: rows.append(v)
tok=defaultdict(lambda:{"sol_in":0.0,"sol_out":0.0,"nbuy":0,"nsell":0,"first":None,"last":None})
for bt,sol_d,mint in rows:
    t=tok[mint]
    if sol_d<-0.002: t["sol_out"]+=-sol_d; t["nbuy"]+=1
    elif sol_d>0.002: t["sol_in"]+=sol_d; t["nsell"]+=1
    if bt:
        t["first"]=bt if t["first"] is None else min(t["first"],bt)
        t["last"]=bt if t["last"] is None else max(t["last"],bt)
toks=[]
for m,t in tok.items():
    if t["sol_out"]<=0 and t["sol_in"]<=0: continue
    net=t["sol_in"]-t["sol_out"]
    hold=(t["last"]-t["first"]) if t["first"] and t["last"] else 0
    toks.append((m,net,t["sol_out"],t["sol_in"],t["nbuy"],t["nsell"],hold))
# only count tokens with both a buy and a sell as a round-trip; buy-only = open
closed=[t for t in toks if t[2]>0 and t[3]>0]
buyonly=[t for t in toks if t[2]>0 and t[3]<=0]
sellonly=[t for t in toks if t[2]<=0 and t[3]>0]
closed.sort(key=lambda x:x[1])
tot=sum(c[1] for c in closed)
wins=[c for c in closed if c[1]>0]; losses=[c for c in closed if c[1]<=0]
print(f"\nrows={len(rows)} tokens touched={len(toks)}")
print(f"=== ROUND-TRIPS (buy+sell same token): {len(closed)} ===")
print(f"realized PnL: {tot:+.2f} SOL")
if closed: print(f"win rate: {len(wins)/len(closed)*100:.1f}%  ({len(wins)}W/{len(losses)}L)")
if wins: print(f"avg win: {sum(c[1] for c in wins)/len(wins):+.3f}")
if losses: print(f"avg loss: {sum(c[1] for c in losses)/len(losses):+.3f}")
holds=[c[6] for c in closed if c[6]>0]
if holds: print(f"median hold: {statistics.median(holds):.0f}s  mean: {sum(holds)/len(holds):.0f}s")
outs=[c[2] for c in closed]
if outs: print(f"median SOL/token (buy total): {statistics.median(outs):.3f}")
print(f"buy-only (still holding): {len(buyonly)}  sell-only (bought before window): {len(sellonly)} netSOLfromSellonly={sum(s[3] for s in sellonly):.1f}")
print("\nTOP 8 WINS:")
for c in sorted(closed,key=lambda x:-x[1])[:8]: print(f"  {c[0][:12]} net={c[1]:+.2f} out={c[2]:.2f} in={c[3]:.2f} nb={c[4]} ns={c[5]} hold={c[6]}s")
print("TOP 6 LOSSES:")
for c in closed[:6]: print(f"  {c[0][:12]} net={c[1]:+.2f} out={c[2]:.2f} in={c[3]:.2f} nb={c[4]} ns={c[5]} hold={c[6]}s")
