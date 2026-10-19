import requests, json, sys, time, random
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict

RPC=open("/root/snipe_study50/rpc_url.txt").read().strip()
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
BUY="e1f7501ed5b38488"; CREATE="b817ee6167c5d33d"
_A="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n=0
    for c in s:n=n*58+_A.index(c)
    full=n.to_bytes((n.bit_length()+7)//8,"big");pad=len(s)-len(s.lstrip("1"));return b"\x00"*pad+full

picks=json.load(open("/root/last500/his_500.json"))
his_mints=set(p["mint"] for p in picks)
cslots=[ (p.get("create_slot") or p.get("create_slot_pre")) for p in picks]
cslots=[c for c in cslots if c]
lo,hi=min(cslots),max(cslots)
print(f"his create_slot range {lo}..{hi} span {hi-lo}",file=sys.stderr)

sess=requests.Session()
def getblock(slot,tries=4):
    for i in range(tries):
        try:
            j=sess.post(RPC,json={"jsonrpc":"2.0","id":1,"method":"getBlock","params":[slot,{"maxSupportedTransactionVersion":1,"transactionDetails":"full","rewards":False,"encoding":"json"}]},timeout=90).json()
            if "result" in j: return j["result"]
            e=j.get("error",{})
            if e.get("code")==-32007: return None
            time.sleep(0.4)
        except: time.sleep(0.5)
    return None

random.seed(7)
sample_slots=sorted(random.sample(range(lo,hi+1), 180))

# pass 1: find creates in sampled slots
def find_creates(slot):
    res=getblock(slot); out=[]
    if not res: return out
    for tx in res["transactions"]:
        meta=tx.get("meta") or {}
        if meta.get("err") is not None: continue
        msg=tx["transaction"]["message"]
        keys=list(msg["accountKeys"])+list((meta.get("loadedAddresses") or {}).get("writable",[]))+list((meta.get("loadedAddresses") or {}).get("readonly",[]))
        allix=list(msg["instructions"])
        for inner in meta.get("innerInstructions",[]): allix+=inner["instructions"]
        for ix in allix:
            pidx=ix.get("programIdIndex")
            if pidx is None or pidx>=len(keys) or keys[pidx]!=PUMP: continue
            d=ix.get("data")
            if not d: continue
            try: raw=b58d(d)
            except: continue
            if raw[:8].hex()!=CREATE: continue
            accs=ix.get("accounts",[])
            if len(accs)<2: continue
            mint=keys[accs[1]]
            if mint not in his_mints: out.append((mint,slot))
    return out

creates=[]
with ThreadPoolExecutor(max_workers=24) as ex:
    for r in ex.map(find_creates, sample_slots): creates.extend(r)
# cap to ~450 random mints
random.shuffle(creates)
creates=creates[:450]
print(f"control mints: {len(creates)}",file=sys.stderr)
ctrl={m:s for m,s in creates}

# pass 2: fetch windows for control mints (create..create+3), collect buyers
need=set()
for m,s in creates:
    for d in range(4): need.add(s+d)
need=sorted(need)
print(f"control window slots: {len(need)}",file=sys.stderr)

def scan_buys(slot):
    res=getblock(slot); out=[]
    if not res: return out
    for tx in res["transactions"]:
        meta=tx.get("meta") or {}
        if meta.get("err") is not None: continue
        msg=tx["transaction"]["message"]
        keys=list(msg["accountKeys"])+list((meta.get("loadedAddresses") or {}).get("writable",[]))+list((meta.get("loadedAddresses") or {}).get("readonly",[]))
        allix=list(msg["instructions"])
        for inner in meta.get("innerInstructions",[]): allix+=inner["instructions"]
        for ix in allix:
            pidx=ix.get("programIdIndex")
            if pidx is None or pidx>=len(keys) or keys[pidx]!=PUMP: continue
            d=ix.get("data")
            if not d: continue
            try: raw=b58d(d)
            except: continue
            if raw[:8].hex()!=BUY: continue
            accs=ix.get("accounts",[])
            if len(accs)<17: continue
            mint=keys[accs[1]]; buyer=keys[accs[8]]
            if mint in ctrl: out.append((mint,slot,buyer))
    return out

allbuys=[]
done=0
with ThreadPoolExecutor(max_workers=24) as ex:
    for r in ex.map(scan_buys, need):
        allbuys.extend(r); done+=1
        if done%150==0: print(f"  {done}/{len(need)}",file=sys.stderr)

# per control mint, set of buyers within window (slot<=create+3)
mint_buyers=defaultdict(set)
for m,slot,buyer in allbuys:
    if slot<=ctrl[m]+3: mint_buyers[m].add(buyer)

# base rate per wallet = #control mints it co-buys / total control mints
from collections import Counter
base=Counter()
for m,bs in mint_buyers.items():
    for w in bs: base[w]+=1
n_ctrl=len(ctrl)
json.dump({"n_ctrl":n_ctrl,"base":dict(base),
           "mints_with_buys":len(mint_buyers)},
          open("/root/caller/control.json","w"))
print(f"control done: n_ctrl={n_ctrl} mints_with_buys={len(mint_buyers)}",file=sys.stderr)
# print base rate for top cohort wallets
cohort=[c["wallet"] for c in json.load(open("/root/caller/cohort.json"))["cohort"]]
print("\nwallet  base_in_ctrl / n_ctrl")
for w in cohort[:15]:
    print(f"{w}  {base.get(w,0)}/{n_ctrl} = {base.get(w,0)/n_ctrl:.3f}")
