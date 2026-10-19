import requests, json, sys, time
sys.path.insert(0,"/root/nonvanilla_re")
from pda import find_pda, ata, b58d, b58e
RPC=open("/root/snipe_study50/rpc_url.txt").read().strip()
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PFEE="pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtE4gUjSGAfvkx"
WALLET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
WSOL="So11111111111111111111111111111111111111112"
TOKENKEG="TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
T22="TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
BUYDISC="e1f7501ed5b38488"
BASELINE=["global","base_mint","quote_mint","base_token_program","quote_token_program","bonding_curve","associated_base_bonding_curve","associated_quote_bonding_curve","user","associated_base_user","associated_quote_user","user_volume_accumulator","fee_config","buyback_fee_recipient","system_program","event_authority","program"]
def rpc(m,p,tries=6):
    for i in range(tries):
        try:
            j=requests.post(RPC,json={"jsonrpc":"2.0","id":1,"method":m,"params":p},timeout=35).json()
            if "result" in j: return j["result"]
            time.sleep(0.5)
        except: time.sleep(0.6)
    return None
def get_tx(sig,ver=0):return rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":ver,"encoding":"jsonParsed"}])
def allkeys(tx):
    msg=tx["transaction"]["message"]; meta=tx.get("meta") or {}
    keys=[a["pubkey"] for a in msg["accountKeys"]]
    la=meta.get("loadedAddresses") or {}
    keys+=la.get("writable",[])+la.get("readonly",[])
    return keys
def find_buy(tx):
    msg=tx["transaction"]["message"]; meta=tx.get("meta") or {}
    allix=list(msg.get("instructions",[]))
    for inr in meta.get("innerInstructions",[]): allix+=inr.get("instructions",[])
    for ix in allix:
        if ix.get("programId")!=PUMP: continue
        d=ix.get("data")
        if not d: continue
        try: raw=b58d(d)
        except: continue
        if raw[:8].hex()!=BUYDISC: continue
        accs=ix.get("accounts",[])
        if len(accs)>8 and accs[8]==WALLET:
            return raw,accs
    return None,None
def owner_of(pk):
    r=rpc("getAccountInfo",[pk,{"encoding":"base64"}])
    if r and r.get("value"): return r["value"]["owner"], r["value"].get("space")
    return None,None

SAMPLES=json.loads(sys.argv[1])
report={}
for kind,(mint,sig,creator) in SAMPLES.items():
    print("\n#############",kind,mint)
    tx=get_tx(sig)
    if not tx: print("  NO TX"); continue
    raw,accs=find_buy(tx)
    if raw is None: print("  NO BUY IX w/ wallet[8]"); continue
    # decode data
    spend=int.from_bytes(raw[8:16],"little"); mto=int.from_bytes(raw[16:24],"little")
    extra=raw[24:]
    print(f"  DATA: disc={raw[:8].hex()} spendable_quote_in={spend} min_tokens_out={mto} rest={extra.hex()} (len_total={len(raw)})")
    print(f"  N_ACCOUNTS={len(accs)}  (baseline=17)")
    # derive expected
    bc,_=find_pda([b"bonding-curve",b58d(mint)],PUMP)
    exp={1:("base_mint",mint),2:("quote_mint",WSOL),5:("bonding_curve",bc),8:("user",WALLET)}
    for i,a in enumerate(accs):
        tag=BASELINE[i] if i<17 else f"EXTRA[{i}]"
        mark=""
        if i in exp and a==exp[i][1]: mark=" <=OK("+exp[i][0]+")"
        elif i in exp: mark=" <=MISMATCH exp="+exp[i][1]
        print(f"   [{i:2}] {tag:34} {a}{mark}")
    # identify extras
    if len(accs)>17:
        print("  --- EXTRA ACCOUNT IDENTIFICATION ---")
        for i in range(17,len(accs)):
            pk=accs[i]; own,space=owner_of(pk)
            print(f"   EXTRA[{i}] {pk} owner={own} space={space}")
            # try pump PDAs
            tests=[
              ("creator-vault[creator]", [b"creator-vault",b58d(creator)], PUMP),
              ("creator-vault[creator]@PFEE", [b"creator-vault",b58d(creator)], PFEE),
              ("creator_vault[creator]@PFEE", [b"creator_vault",b58d(creator)], PFEE),
              ("fee_config@PFEE", [b"fee_config",b58d(PUMP)], PFEE),
              ("global_volume_accumulator", [b"global_volume_accumulator"], PUMP),
              ("user_volume_accumulator[user]", [b"user_volume_accumulator",b58d(WALLET)], PUMP),
              ("holder-reward[mint]", [b"holder-reward",b58d(mint)], PUMP),
              ("holder_reward[mint]", [b"holder_reward",b58d(mint)], PUMP),
              ("holder-rewards[mint]", [b"holder-rewards",b58d(mint)], PUMP),
              ("sharing-config[mint]", [b"sharing-config",b58d(mint)], PUMP),
              ("cashback[user]", [b"cashback",b58d(WALLET)], PUMP),
              ("creator-vault[mint]", [b"creator-vault",b58d(mint)], PUMP),
            ]
            for name,seeds,prog in tests:
                try:
                    d,b=find_pda(seeds,prog)
                    if d==pk: print(f"       == PDA MATCH: {name} (prog={prog}) bump={b}")
                except Exception as e: pass
json.dump(report,open("/root/nonvanilla_re/decoded.json","w"))
