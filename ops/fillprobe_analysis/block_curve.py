import json, os, sys, urllib.request, time
URL=os.environ["CKURL"]
def rpc(method,params):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    for a in range(6):
        try:
            req=urllib.request.Request(URL,data=body,headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req,timeout=60) as r: d=json.load(r)
            if "error" in d: sys.stderr.write(f"err {d['error']}\n"); time.sleep(0.8); continue
            return d["result"]
        except Exception as e: sys.stderr.write(f"a{a} {e}\n"); time.sleep(1.0)
    return None

PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

def allkeys(tx):
    msg=tx["transaction"]["message"]
    keys=[k["pubkey"] if isinstance(k,dict) else k for k in msg["accountKeys"]]
    lmeta=tx["meta"].get("loadedAddresses") or {}
    keys=keys+lmeta.get("writable",[])+lmeta.get("readonly",[])
    return keys

def analyze(slot, curve, mint, our_payer):
    blk=rpc("getBlock",[slot,{"encoding":"jsonParsed","transactionDetails":"full","maxSupportedTransactionVersion":1,"rewards":False}])
    if not blk:
        return None
    out=[]
    for idx,tx in enumerate(blk["transactions"]):
        keys=allkeys(tx)
        if curve not in keys: continue
        m=tx["meta"]
        sig=tx["transaction"]["signatures"][0]
        payer=keys[0]
        # curve token balance after
        rtok_post=None; rtok_pre=None
        for tb in m.get("postTokenBalances",[]):
            if tb["mint"]==mint and tb["owner"]==curve: rtok_post=int(tb["uiTokenAmount"]["amount"])
        for tb in m.get("preTokenBalances",[]):
            if tb["mint"]==mint and tb["owner"]==curve: rtok_pre=int(tb["uiTokenAmount"]["amount"])
        # curve lamports
        cidx=keys.index(curve)
        clam_pre=m["preBalances"][cidx]; clam_post=m["postBalances"][cidx]
        # tokens received by buyer (payer owner) for this mint
        buyer_tok_pre=0; buyer_tok_post=0
        for tb in m.get("preTokenBalances",[]):
            if tb["mint"]==mint and tb["owner"]==payer: buyer_tok_pre=int(tb["uiTokenAmount"]["amount"])
        for tb in m.get("postTokenBalances",[]):
            if tb["mint"]==mint and tb["owner"]==payer: buyer_tok_post=int(tb["uiTokenAmount"]["amount"])
        out.append({
            "block_index":idx,"sig":sig,"payer":payer,"is_ours":payer==our_payer,
            "rtok_pre":rtok_pre,"rtok_post":rtok_post,
            "clam_pre":clam_pre,"clam_post":clam_post,
            "curve_lam_delta":clam_post-clam_pre,
            "curve_tok_delta":(rtok_post-rtok_pre) if (rtok_post is not None and rtok_pre is not None) else None,
            "buyer_tok_delta":buyer_tok_post-buyer_tok_pre,
            "err":m["err"]
        })
    return {"slot":slot,"parent_slot":blk.get("parentSlot"),"n_curve_tx":len(out),"txs":out}

if __name__=="__main__":
    slot=int(sys.argv[1]); curve=sys.argv[2]; mint=sys.argv[3]; payer=sys.argv[4]
    print(json.dumps(analyze(slot,curve,mint,payer)))
