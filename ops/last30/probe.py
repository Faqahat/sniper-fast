import rpc, json, sys
from enrich import b58d, PUMP, CB, CREATE, BUYS, W
pos={x["mint"]:x for x in json.load(open("/root/last30/positions.json"))["positions"]}
# a 'None' rank mint and a 'rank1' mint
for mint in ["4GeVakyp","GsRoHYCE","EgwYSm32"]:
    full=[m for m in pos if m.startswith(mint)][0]
    p=pos[full]
    tx=rpc.gettx(p["sig"])
    msg=tx["transaction"]["message"]
    keys=[k["pubkey"] if isinstance(k,dict) else k for k in msg["accountKeys"]]
    signer=keys[0]
    # find pump instructions (top + inner)
    discs=[]
    def scan(ixs):
        for ix in ixs:
            pid=ix.get("programId")
            if pid==PUMP:
                d=ix.get("data")
                try: raw=b58d(d)
                except: continue
                discs.append(raw[:8].hex())
    scan(msg.get("instructions",[]))
    for inner in tx["meta"].get("innerInstructions",[]):
        scan(inner["instructions"])
    print(mint,"buy_slot",p["slot"],"signer==W?",signer==W,"signer",signer[:6],"pump_discs",discs,"known",[BUYS.get(x) for x in discs])
