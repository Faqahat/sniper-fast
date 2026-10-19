import json,urllib.request,os,time,concurrent.futures as cf
from collections import defaultdict
TOK=os.environ["CONSTANTK_TOKEN"]
RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
W="CUQqcZZGr8QLjEzMpxUZyiZirBujE2Y9yZDyfCRw1CAB"
def rpc(m,p):
    req=urllib.request.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={"content-type":"application/json"})
    for i in range(5):
        try: return json.load(urllib.request.urlopen(req,timeout=25)).get("result")
        except: time.sleep(0.4*(i+1))
    return None
# all sigs
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
    # token balance change for W
    pre={b["mint"]:float(b["uiTokenAmount"]["uiAmount"] or 0) for b in meta.get("preTokenBalances",[]) if b.get("owner")==W}
    post={b["mint"]:float(b["uiTokenAmount"]["uiAmount"] or 0) for b in meta.get("postTokenBalances",[]) if b.get("owner")==W}
    SKIP={"So11111111111111111111111111111111111111112","EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v","Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"}
    mints=(set(pre)|set(post))-SKIP
    tok_mint=None;tok_d=0
    for m in mints:
        d=post.get(m,0)-pre.get(m,0)
        if abs(d)>abs(tok_d): tok_d=d; tok_mint=m
    bt=tx.get("blockTime")
    return (bt,sol_d,tok_mint,tok_d)
rows=[]
with cf.ThreadPoolExecutor(max_workers=8) as ex:
    for v in ex.map(lambda s: parse(s["signature"]), sigs):
        if v and v[2]: rows.append(v)
print("rows with token mint:",len(rows))
from collections import Counter
mc=Counter(r[2] for r in rows)
print("unique tokens touched:",len(mc))
print("sample rows:", rows[:3])
# group by mint
tok=defaultdict(lambda:{"sol_in":0,"sol_out":0,"tok_bought":0,"tok_sold":0,"first":None,"last":None,"nbuy":0,"nsell":0})
for bt,sol_d,mint,tok_d in rows:
    t=tok[mint]
    if tok_d>0:  # received tokens = BUY
        t["sol_out"]+=-sol_d if sol_d<0 else 0; t["tok_bought"]+=tok_d; t["nbuy"]+=1
    elif tok_d<0:  # sent tokens = SELL
        t["sol_in"]+=sol_d if sol_d>0 else 0; t["tok_sold"]+=-tok_d; t["nsell"]+=1
    if bt:
        if t["first"] is None or bt<t["first"]: t["first"]=bt
        if t["last"] is None or bt>t["last"]: t["last"]=bt
# PnL per token (only fully/mostly exited: sold>=90% of bought)
closed=[];open_pos=[]
for m,t in tok.items():
    if t["tok_bought"]<=0: continue
    net=t["sol_in"]-t["sol_out"]
    exited=t["tok_sold"]/t["tok_bought"] if t["tok_bought"] else 0
    hold=(t["last"]-t["first"]) if t["first"] and t["last"] else 0
    rec=(m,net,t["sol_out"],t["sol_in"],exited,hold,t["nbuy"],t["nsell"])
    if exited>=0.9: closed.append(rec)
    else: open_pos.append(rec)
closed.sort(key=lambda x:x[1])
tot=sum(c[1] for c in closed)
wins=[c for c in closed if c[1]>0]; losses=[c for c in closed if c[1]<=0]
print(f"\n=== CLOSED round-trips: {len(closed)} tokens ===")
print(f"realized PnL: {tot:+.2f} SOL")
print(f"win rate: {len(wins)/max(1,len(closed))*100:.1f}%  ({len(wins)}W/{len(losses)}L)")
if wins: print(f"avg win: {sum(c[1] for c in wins)/len(wins):+.3f}  avg loss: {sum(c[1] for c in losses)/len(losses):+.3f}" if losses else "")
import statistics
holds=[c[5] for c in closed if c[5]>0]
if holds: print(f"median hold: {statistics.median(holds):.0f}s  mean hold: {sum(holds)/len(holds):.0f}s")
sizes=[c[2] for c in closed if c[2]>0]
if sizes: print(f"median buy total/token: {statistics.median(sizes):.3f} SOL")
print(f"\nopen/partial positions: {len(open_pos)} tokens (still holding)")
print("\nTOP 8 WINS:")
for c in sorted(closed,key=lambda x:-x[1])[:8]: print(f"  {c[0][:12]} net={c[1]:+.2f} out={c[2]:.2f} in={c[3]:.2f} hold={c[5]}s")
print("TOP 6 LOSSES:")
for c in closed[:6]: print(f"  {c[0][:12]} net={c[1]:+.2f} out={c[2]:.2f} in={c[3]:.2f} hold={c[5]}s")
