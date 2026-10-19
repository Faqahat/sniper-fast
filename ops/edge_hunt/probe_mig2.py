import sys,os,json
sys.path.insert(0,"/root/profit_backtest")
import common as C
PUMPSWAP="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
mint="2t6Z9BiZBkyoxq3gH7nn9mD269MU3YdM6PW1a9NGpump"
bc=C.bonding_curve_of(mint)
# NEWEST sigs first (no before) - migration is near the newest curve activity
ch=C.rpc("getSignaturesForAddress",[bc,{"limit":30}])
print("newest curve sigs (slot):",[s["slot"] for s in ch[:12]])
for s in ch[:12]:
    tx=C.gettx(s["signature"])
    if not tx or not tx.get("meta"): continue
    meta=tx["meta"]; keys=C._keys(tx)
    dsol=0
    if bc in keys:
        idx=keys.index(bc); dsol=(meta["postBalances"][idx]-meta["preBalances"][idx])/1e9
    progs=set(ix.get("programId") for ix in tx["transaction"]["message"].get("instructions",[]))
    hasps = PUMPSWAP in keys
    print(f" slot {s['slot']} dsol {dsol:+.2f} pumpswap_in_keys={hasps} err={s['err']}")
    if dsol<-40 or hasps:
        print("   -> MIGRATION candidate. sig",s["signature"])
        print("   top progs:",progs)
        # token holders post
        for t in meta.get("postTokenBalances",[]):
            if t.get("mint")==mint and float(t["uiTokenAmount"]["uiAmountString"] or 0)>1000:
                print("   mint holder:",t.get("owner"),"amt",t["uiTokenAmount"]["uiAmountString"])
        # find pumpswap-owned accounts / pool: scan keys
        print("   keys:",[k for k in keys])
        break
