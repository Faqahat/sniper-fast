import sys,json; sys.path.insert(0,"/root/profit_backtest"); import common as C
d=json.load(open("/root/edge_hunt/thesis2_pools_v2.json"))
r=next(x for x in d if x.get("mint","").startswith("kifZWTMe"))
mint=r["mint"]; pool=r["pool"]; mig=r["mig_slot"]
WSOL="So11111111111111111111111111111111111111112"
# get swaps via pool sigs forward
ch=C.rpc("getSignaturesForAddress",[pool,{"limit":1000}])
sw=sorted([s for s in ch if not s["err"] and s["slot"]>=mig],key=lambda x:x["slot"])[:5]
print("mint",mint,"pool",pool,"mig",mig)
for s in sw:
    tx=C.gettx(s["signature"]); meta=tx["meta"]; kk=C._keys(tx)
    print(f"\n--- slot {s['slot']} sig {s['signature'][:16]} ---")
    # all token balance changes for this mint and WSOL, by account
    for which,mtok in [("TOK",mint),("WSOL",WSOL)]:
        pre={}; post={}
        for tb in meta.get("preTokenBalances",[]):
            if tb["mint"]==mtok: pre[tb["accountIndex"]]=float(tb["uiTokenAmount"]["uiAmountString"] or 0)
        for tb in meta.get("postTokenBalances",[]):
            if tb["mint"]==mtok: post[tb["accountIndex"]]=float(tb["uiTokenAmount"]["uiAmountString"] or 0)
        for ai in sorted(set(pre)|set(post)):
            dv=post.get(ai,0)-pre.get(ai,0)
            if abs(dv)>1e-9:
                print(f"   {which} acct[{ai}] {kk[ai][:12]} {pre.get(ai,0):.4f}->{post.get(ai,0):.4f} d={dv:+.4f}")
