import os, sys, json, time, hashlib, threading
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,"/root/tmp_creator")
from analyze import rpc, b58decode, PUMP

CREATE_DISC = hashlib.sha256(b"global:create").digest()[:8]
sigs=json.load(open("/root/tmp_creator/sigs.json"))
succ=[s["signature"] for s in sigs if not s.get("err")]
print("successful sigs:", len(succ), flush=True)

mints={}
lock=threading.Lock()
done=[0]

def classify(sig):
    tx=rpc("getTransaction",[sig,{"encoding":"jsonParsed","maxSupportedTransactionVersion":0}])
    m=None
    if tx:
        msg=tx["transaction"]["message"]
        instrs=list(msg.get("instructions",[]))
        for inner in tx.get("meta",{}).get("innerInstructions",[]) or []:
            instrs+=inner.get("instructions",[])
        for ix in instrs:
            if ix.get("programId")==PUMP and "data" in ix:
                try: data=b58decode(ix["data"])
                except Exception: continue
                if data[:8]==CREATE_DISC:
                    accs=ix.get("accounts",[])
                    if accs: m=accs[0]; break
    with lock:
        done[0]+=1
        if m and m not in mints:
            mints[m]=sig
            json.dump(mints,open("/root/tmp_creator/mints.json","w"))
        if done[0]%300==0:
            print("processed",done[0],"creates",len(mints),flush=True)

with ThreadPoolExecutor(max_workers=24) as ex:
    list(ex.map(classify, succ))

json.dump(mints,open("/root/tmp_creator/mints.json","w"))
print("DONE distinct mints:", len(mints), flush=True)
