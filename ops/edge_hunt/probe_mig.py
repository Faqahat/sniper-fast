import sys,os,json
sys.path.insert(0,"/root/profit_backtest")
import common as C
PUMPSWAP="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
mint="2t6Z9BiZBkyoxq3gH7nn9mD269MU3YdM6PW1a9NGpump"
bc=C.bonding_curve_of(mint)
cs=456604917
# paginate full sig list
allsigs=[]; before=None
while True:
    pr=[bc,{"limit":1000}]
    if before: pr[1]["before"]=before
    ch=C.rpc("getSignaturesForAddress",pr)
    if not ch: break
    allsigs+=ch; before=ch[-1]["signature"]
    if len(ch)<1000: break
    if ch[-1]["slot"]<=cs: break
sigs=[s for s in allsigs if not s["err"]]
sigs.sort(key=lambda s:s["slot"])
print(f"total curve txs {len(sigs)} slots {sigs[0]['slot']}..{sigs[-1]['slot']}")
# find big withdraw (migration)
mig=None
for s in sigs:
    tx=C.gettx(s["signature"])
    if not tx or not tx.get("meta"): continue
    meta=tx["meta"]; keys=C._keys(tx)
    if bc in keys:
        idx=keys.index(bc); dsol=(meta["postBalances"][idx]-meta["preBalances"][idx])/1e9
        if dsol<-50:
            mig=(s,tx,dsol); break
if not mig:
    # fallback: last curve tx
    s=sigs[-1]; mig=(s,C.gettx(s["signature"]),None)
s,tx,dsol=mig
print(f"\nMIGRATION tx slot {s['slot']} dsol {dsol}")
print("sig",s["signature"])
msg=tx["transaction"]["message"]; keys=C._keys(tx)
# programs invoked
progs=set()
for ix in msg.get("instructions",[]):
    progs.add(ix.get("programId"))
    for inner in tx["meta"].get("innerInstructions",[]):
        pass
print("top-level programs:",progs)
# inner instruction programs
innerprogs=set()
for grp in tx["meta"].get("innerInstructions",[]):
    for ix in grp.get("instructions",[]):
        innerprogs.add(ix.get("programId"))
print("inner programs:",innerprogs)
print("PumpSwap in keys?", PUMPSWAP in keys)
# find accounts owned by/related to PumpSwap - look at postTokenBalances owners
owners=set(t.get("owner") for t in tx["meta"].get("postTokenBalances",[]))
print("postTokenBalance owners:",owners)
# which accounts hold the mint after migration
for t in tx["meta"].get("postTokenBalances",[]):
    if t.get("mint")==mint:
        print("  holds mint:",t.get("owner"),"amt",t["uiTokenAmount"]["uiAmountString"])
# dump all keys that aren't the usual
print("\nall account keys:")
for i,k in enumerate(keys): print(" ",i,k)
