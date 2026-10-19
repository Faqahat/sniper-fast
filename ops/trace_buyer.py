import json,urllib.request,os,time,hashlib
TOK=os.environ["CONSTANTK_TOKEN"]
RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
W="CUQqcZZGr8QLjEzMpxUZyiZirBujE2Y9yZDyfCRw1CAB"
MINT="8rUNtrzTk5D4GDjro4KFYhndBetfGnKsi1FJmMNbpump"
B58="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58dec(s):
    n=0
    for c in s: n=n*58+B58.index(c)
    return n.to_bytes((n.bit_length()+7)//8,"big")
def b58enc(b):
    n=int.from_bytes(b,"big");o=""
    while n>0:n,r=divmod(n,58);o=B58[r]+o
    return "1"*(len(b)-len(b.lstrip(b"\x00")))+o
def rpc(m,p):
    req=urllib.request.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={"content-type":"application/json"})
    for i in range(5):
        try: return json.load(urllib.request.urlopen(req,timeout=25)).get("result")
        except: time.sleep(0.4*(i+1))
    return None
# find W's token account(s) for MINT (both token programs)
for prog in ["TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA","TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"]:
    r=rpc("getTokenAccountsByOwner",[W,{"mint":MINT},{"encoding":"jsonParsed"}])
    if r and r.get("value"):
        for a in r["value"]:
            print("W token acct:",a["pubkey"])
# get signatures on W's ATA to find who credited it
ata=None
r=rpc("getTokenAccountsByOwner",[W,{"mint":MINT},{"encoding":"jsonParsed"}])
if r and r.get("value"): ata=r["value"][0]["pubkey"]
if not ata:
    # account may be closed after sell; derive ATA for token-2022
    ATAPROG=b58dec("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
    T22=b58dec("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")
    seed=b58dec(W)+T22+b58dec(MINT)
    P=2**255-19
    def oc(yb):
        y=int.from_bytes(yb,"little")&((1<<255)-1)
        if y>=P:return False
        d=(-121665*pow(121666,P-2,P))%P;u=(y*y-1)%P;v=(d*y*y+1)%P;xx=(u*pow(v,P-2,P))%P;x=pow(xx,(P+3)//8,P)
        if (x*x-xx)%P!=0:x=(x*pow(2,(P-1)//4,P))%P
        return (x*x-xx)%P==0
    for b in range(255,-1,-1):
        h=hashlib.sha256(seed+bytes([b])+ATAPROG+b"ProgramDerivedAddress").digest()
        if not oc(h): ata=b58enc(h);break
print("ATA:",ata)
sgs=rpc("getSignaturesForAddress",[ata,{"limit":30}])
print("ATA sigs:",len(sgs) if sgs else 0)
# inspect earliest (credit) txs
for s in (sgs[::-1][:6] if sgs else []):
    tx=rpc("getTransaction",[s["signature"],{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
    if not tx: continue
    keys=[k["pubkey"] for k in tx["transaction"]["message"]["accountKeys"]]
    signers=[k["pubkey"] for k in tx["transaction"]["message"]["accountKeys"] if k.get("signer")]
    logs=tx["meta"].get("logMessages",[])
    kind="BUY" if any("Instruction: Buy" in l for l in logs) else ("SELL" if any("Instruction: Sell" in l for l in logs) else "xfer")
    # W ATA token delta
    pre=next((float(b["uiTokenAmount"]["uiAmount"] or 0) for b in tx["meta"].get("preTokenBalances",[]) if b.get("owner")==W),0)
    post=next((float(b["uiTokenAmount"]["uiAmount"] or 0) for b in tx["meta"].get("postTokenBalances",[]) if b.get("owner")==W),0)
    fp=signers[0] if signers else "?"
    fpsol=0
    if fp in keys:
        i=keys.index(fp);fpsol=(tx["meta"]["postBalances"][i]-tx["meta"]["preBalances"][i])/1e9
    print(f"  {s['signature'][:12]} {kind} fee_payer={fp[:10]} payerSOLΔ={fpsol:+.3f} W_tokΔ={post-pre:+.0f}")
