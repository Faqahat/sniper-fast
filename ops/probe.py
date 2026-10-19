import json, urllib.request, os
from concurrent.futures import ThreadPoolExecutor
RPC = "https://rpc-frankfurt.constant-k.com/?api-key=" + os.environ["CONSTANTK_TOKEN"]
def rpc(method, params):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    req = urllib.request.Request(RPC, data=body, headers={"Content-Type":"application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())["result"]
sigs=json.load(open("/root/wallet_sigs.json"))
good=[s for s in sigs if not s["err"]]
def get(s): return s, rpc("getTransaction",[s,{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
import collections
instr_counter=collections.Counter()
sample=good[:60]
with ThreadPoolExecutor(20) as ex:
    for s,tx in ex.map(get,[x["sig"] for x in sample]):
        logs=tx["meta"].get("logMessages",[])
        instrs=[l.split("Instruction: ")[1] for l in logs if "Instruction: " in l]
        instr_counter[tuple(sorted(set(instrs)))]+=1
for k,v in instr_counter.most_common():
    print(v, k)
