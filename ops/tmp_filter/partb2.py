import sys; sys.path.insert(0,"/root/tmp_filter")
from rpc import sigs,tx,parse_curve
MINT="HNwcHVQeV9MqbR9KhEWZK62Mfv48awKh4RCtxmMbpump"
ss=sigs(MINT,1000)
ss=ss[::-1]  # oldest first
print("all txs on mint:",len(ss))
curve=None
for i,s in enumerate(ss):
    t=tx(s["signature"])
    msg=t["transaction"]["message"]; meta=t["meta"]
    keys=[k["pubkey"] for k in msg["accountKeys"]]
    signer=keys[0]
    pre=meta["preBalances"]; post=meta["postBalances"]
    sd=(post[0]-pre[0])/1e9
    insts=[l.split("Instruction: ")[1] for l in meta.get("logMessages",[]) if "Instruction: " in l]
    act=[x for x in insts if x in ("CreateV2","BuyV2","SellV2","Buy","Sell","CreateV1","Create")]
    # find pump-owned curve account & its token balance change
    print("tx%d slot=%d signer=%s..%s solDelta=%+.4f acts=%s"%(
        i,s["slot"],signer[:4],signer[-4:],sd,act))
    # token balances for this signer
    for tb in (meta.get("postTokenBalances") or []):
        if tb.get("owner")==signer:
            amt=tb["uiTokenAmount"]["uiAmount"]
            print("     signer token bal after: %s"%amt)
# find the bonding curve: scan create tx for pump-owned writable account
t0=tx(ss[0]["signature"])
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
msg=t0["transaction"]["message"]
for k in msg["accountKeys"]:
    if k.get("pubkey") and k["pubkey"]!=MINT:
        c=parse_curve(k["pubkey"])
        if c and c.get("supply",0)>0:
            print("CURVE",k["pubkey"][:6],c); break
