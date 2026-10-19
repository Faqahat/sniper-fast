#!/usr/bin/env python3
"""Target-wallet confirmation. For each of 4yFAz...'s ~200 sniped mints, apply the SAME slot-0
insider-bundle classification on the create_slot block, and locate where HE landed relative to the
create + insiders (block index in create slot, or slot delta if he landed later)."""
import os, json, sys, time, threading
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,"/root/bundle_signal")
import classify as C   # reuse decode_tx, get_block, b58d, discriminators, JITO

TARGET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
CACHE="/root/bundle_signal/targetfeat"; os.makedirs(CACHE,exist_ok=True)

def analyze(rec):
    mint=rec["mint"]; cslot=rec["create_slot"]; his_sig=rec["sig"]; his_slot=rec["slot"]
    fp=os.path.join(CACHE,mint+".json")
    if os.path.exists(fp):
        try: return json.load(open(fp))
        except: pass
    blk=C.get_block(cslot)
    if not blk:
        out={"mint":mint,"error":"noblock"}; json.dump(out,open(fp,"w")); return out
    txs=blk["transactions"]; dec=[C.decode_tx(tx) for tx in txs]
    # create tx index: find pump create for this mint
    create_idx=None
    for idx,d in enumerate(dec):
        if d["is_create"] and mint in d["allk"]: create_idx=idx; break
    if create_idx is None:
        out={"mint":mint,"error":"nocreate","n_txs":len(txs)}; json.dump(out,open(fp,"w")); return out
    cd=dec[create_idx]
    jito_tip=cd["jito_tip"]; create_cu=cd["cu_price"]
    adj_zero=0; adj_zero_anymint=0
    for j in range(create_idx+1, min(create_idx+5, len(txs))):
        dj=dec[j]
        if dj["is_buy"] and dj["cu_price"]==0 and not dj["err"]:
            adj_zero_anymint+=1
            if mint in dj["allk"]: adj_zero+=1
    comp_cu=[]; n_buys=0
    for idx,d in enumerate(dec):
        if idx==create_idx: continue
        if d["is_buy"] and (mint in d["allk"]) and not d["err"]:
            n_buys+=1; comp_cu.append(d["cu_price"])
    max_comp=max(comp_cu) if comp_cu else 0
    bundled = (jito_tip>0) or (adj_zero>=1)
    # locate HIS buy. Same slot as create? find his sig in this block.
    his_idx_in_create=None
    for idx,tx in enumerate(txs):
        s=tx['transaction'].get('signatures',[])
        if s and s[0]==his_sig: his_idx_in_create=idx; break
    his_delta_slots=his_slot-cslot
    # did he land ahead of insiders? only meaningful if same slot and bundled via adjacency.
    # insider block indices = create_idx+1..+4 with zero-fee this-mint buys
    insider_idxs=[j for j in range(create_idx+1,min(create_idx+5,len(txs)))
                  if dec[j]["is_buy"] and dec[j]["cu_price"]==0 and (mint in dec[j]["allk"]) and not dec[j]["err"]]
    ahead=None
    if his_idx_in_create is not None and insider_idxs:
        ahead = his_idx_in_create < min(insider_idxs)
    out={"mint":mint,"create_slot":cslot,"create_idx":create_idx,"n_txs":len(txs),
         "jito_tip_on_create":jito_tip,"create_cu_price":create_cu,
         "adjacent_zero_fee_buys":adj_zero,"adjacent_zero_fee_buys_anymint":adj_zero_anymint,
         "max_competitor_cu_price":max_comp,"n_buys_in_create_slot":n_buys,"bundled":bundled,
         "his_slot":his_slot,"his_delta_slots":his_delta_slots,
         "his_idx_in_create_slot":his_idx_in_create,"his_cu_price":rec.get("cu_price"),
         "insider_idxs":insider_idxs,"his_ahead_of_insiders":ahead}
    json.dump(out,open(fp,"w")); return out

if __name__=="__main__":
    d=json.load(open("/root/snipe_study50/enriched200.json"))
    recs=d["records"]
    # keep records with a create_slot
    recs=[r for r in recs if r.get("create_slot")]
    print(f"target records: {len(recs)}",flush=True)
    results=[]; done=0; errs=0; t0=time.time()
    with ThreadPoolExecutor(max_workers=16) as ex:
        for r in ex.map(analyze, recs):
            results.append(r); done+=1
            if r.get("error"): errs+=1
            if done%50==0: print(f"  {done}/{len(recs)} errs={errs} {time.time()-t0:.0f}s",flush=True)
    json.dump(results,open("/root/bundle_signal/target_classify.json","w"),indent=0)
    good=[r for r in results if not r.get("error")]
    bundled=sum(1 for r in good if r.get("bundled"))
    print(f"done {done} errs={errs} good={len(good)} in {time.time()-t0:.0f}s")
    print(f"TARGET BUNDLED={bundled}/{len(good)} ({100*bundled/len(good):.1f}%)")
