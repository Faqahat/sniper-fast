import requests, json, sys, time
sys.path.insert(0,"/root/nonvanilla_re")
from pda import find_pda, b58d, b58e
RPC=open("/root/snipe_study50/rpc_url.txt").read().strip()
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PFEE="pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtE4gUjSGAfvkx"
def rpc(m,p,tries=5):
    for i in range(tries):
        try:
            j=requests.post(RPC,json={"jsonrpc":"2.0","id":1,"method":m,"params":p},timeout=35).json()
            if "result" in j: return j["result"]
            time.sleep(0.5)
        except: time.sleep(0.6)
    return None
def ai(pk):
    r=rpc("getAccountInfo",[pk,{"encoding":"base64"}])
    if r and r.get("value"):
        import base64
        return r["value"]["owner"], base64.b64decode(r["value"]["data"][0])
    return None,None
# fee_config constant
FC="8Wf5TiAheLUqBrKXeYg2JtAFFMWtKdG2BSFgqUcPVwTt"
own,data=ai(FC)
print("fee_config",FC,"owner",own,"len",len(data) if data else None)
# derive fee_config PDA under pfee: seeds candidates
for name,seeds,prog in [("fee_config[pump]@PFEE",[b"fee_config",b58d(PUMP)],PFEE),
                         ("fee_config@PFEE",[b"fee_config"],PFEE),
                         ("fee_config[pump]@PUMP",[b"fee_config",b58d(PUMP)],PUMP)]:
    d,b=find_pda(seeds,prog); print("  try",name,"=>",d,"MATCH" if d==FC else "")
# dump fee_config data as list of 32-byte pubkeys to find buyback recipients
if data:
    print("  --- fee_config pubkey scan (offsets where a known buyback recipient sits) ---")
    recips=["EHAAiTxcdDwQ3U4bU6YcMsQGaekdzLS3B5SmYo46kJtL","5eHhjP8JaYkz83CWwvGU2uMUXefd3AazWGx4gpcuEEYD","9M4giFFMxmFGXtc3feFzRai56WbBqehoSeRE5GK7gf7","5YxQFdt3Tr9zJLvkFccqXVUwhdTWJQc1fFg2YPbxvxeD","GXPFM2caqTtQYC2cJ5yJRi9VDkpsYZXzYdwYpGnLmtDL"]
    rb={r:b58d(r) for r in recips}
    for off in range(0,len(data)-32+1,8):
        chunk=data[off:off+32]
        for r,rbv in rb.items():
            if chunk==rbv: print(f"    off {off}: {r}")
    # also print all 32-byte aligned pubkeys from offset 8
    print("  all 32B slots from off 8 (first 24):")
    off=8;n=0
    while off+32<=len(data) and n<24:
        print("    off",off,b58e(data[off:off+32])); off+=32;n+=1
