import rpc,json
snipes=json.load(open("/root/snipe_study50/snipes200.json"))["snipes"]
W=rpc.WALLET
def parse_trade(tx,mint,ata_pubkey=None):
    m=tx["meta"]
    if m.get("err"): return None
    keys=[k["pubkey"] if isinstance(k,dict) else k for k in tx["transaction"]["message"]["accountKeys"]]
    pre=m["preBalances"]; post=m["postBalances"]
    # token balances for this mint
    preT={b["accountIndex"]:int(b["uiTokenAmount"]["amount"]) for b in m.get("preTokenBalances",[]) if b["mint"]==mint}
    postT={b["accountIndex"]:int(b["uiTokenAmount"]["amount"]) for b in m.get("postTokenBalances",[]) if b["mint"]==mint}
    owners={b["accountIndex"]:b.get("owner") for b in m.get("preTokenBalances",[])+m.get("postTokenBalances",[]) if b["mint"]==mint}
    # wallet token delta (his ATA: owner==W)
    wal_idx=[i for i,o in owners.items() if o==W]
    curve_idx=[i for i,o in owners.items() if o and o!=W]
    def td(i): return postT.get(i,0)-preT.get(i,0)
    wtok=sum(td(i) for i in wal_idx)
    ctok=sum(td(i) for i in curve_idx)
    # curve SOL delta: bonding curve account = owner pubkey of curve vault; find its key index
    curve_owner=owners[curve_idx[0]] if curve_idx else None
    csol=None
    if curve_owner:
        for i,k in enumerate(keys):
            if k==curve_owner: csol=post[i]-pre[i]; break
    wsol=post[0]-pre[0]  # wallet lamport delta (keys[0] is fee payer=wallet for his txs)
    feepayer=keys[0]
    return dict(slot=tx["slot"],bt=tx.get("blockTime"),wtok=wtok,ctok=ctok,csol=csol,wsol=wsol,feepayer=feepayer,curve=curve_owner)

for d in snipes[:3]:
    mint=d["mint"]
    btx=rpc.gettx(d["sig"])
    tr=parse_trade(btx,mint)
    # find ATA pubkey
    m=btx["meta"]; keys=[k["pubkey"] if isinstance(k,dict) else k for k in btx["transaction"]["message"]["accountKeys"]]
    ataidx=[b["accountIndex"] for b in m.get("postTokenBalances",[]) if b["mint"]==mint and b.get("owner")==W]
    ata=keys[ataidx[0]] if ataidx else None
    print("MINT",mint[:10],"BUY slot",d["slot"],"tok",tr["wtok"],"csol",tr["csol"],"wsol",tr["wsol"],"curve",(tr["curve"] or "")[:10],"ATA",(ata or "")[:10])
    # page his sigs on ATA
    sigs=rpc.getsigs(ata,limit=1000)
    print("  ATA nsigs",len(sigs))
    for s in sigs:
        print("   sig slot",s["slot"],"err",bool(s.get("err")))
