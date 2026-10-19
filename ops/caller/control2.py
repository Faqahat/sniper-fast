import requests, json, sys, time, random
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict, Counter

RPC=open("/root/snipe_study50/rpc_url.txt").read().strip()
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
BUY="e1f7501ed5b38488"
_A="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n=0
    for c in s:n=n*58+_A.index(c)
    full=n.to_bytes((n.bit_length()+7)//8,"big");pad=len(s)-len(s.lstrip("1"));return b"\x00"*pad+full

picks=json.load(open("/root/last500/his_500.json"))
cslots=[(p.get("create_slot") or p.get("create_slot_pre")) for p in picks]; cslots=[c for c in cslots if c]
lo,hi=min(cslots),max(cslots)
random.seed(11)
# sample contiguous mini-ranges to capture create windows realistically: 300 random blocks
sample=sorted(random.sample(range(lo,hi+1),300))

cohort=set(c["wallet"] for c in json.load(open("/root/caller/cohort.json"))["cohort"])
TARGET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
cohort.add(TARGET)

sess=requests.Session()
def getblock(slot,tries=4):
    for i in range(tries):
        try:
            j=sess.post(RPC,json={"jsonrpc":"2.0","id":1,"method":"getBlock","params":[slot,{"maxSupportedTransactionVersion":1,"transactionDetails":"full","rewards":False,"encoding":"json"}]},timeout=90).json()
            if "result" in j: return j["result"]
            if j.get("error",{}).get("code")==-32007: return None
            time.sleep(0.4)
        except: time.sleep(0.5)
    return None

def scan(slot):
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
            out.append((keys[accs[1]],keys[accs[8]]))  # (mint,buyer)
    return out

pairs=[]
done=0; total_buys=0
with ThreadPoolExecutor(max_workers=24) as ex:
    for r in ex.map(scan,sample):
        pairs.extend(r); done+=1
        if done%75==0: print(f"  {done}/{len(sample)} blocks {len(pairs)} buys",file=sys.stderr)

# distinct mints bought per wallet (in random blocks)
wallet_mints=defaultdict(set); all_mints=set()
for mint,buyer in pairs:
    wallet_mints[buyer].add(mint); all_mints.add(mint)
nblocks=len(sample); ndistinct=len(all_mints)
print(f"\nrandom sample: {nblocks} blocks, {len(pairs)} buys, {ndistinct} distinct mints bought",file=sys.stderr)
print("\n=== cohort wallet activity in random blocks (distinct mints bought) ===")
res={}
for w in sorted(cohort, key=lambda x:-len(wallet_mints.get(x,()))):
    n=len(wallet_mints.get(w,()))
    res[w]=n
    tag=" <-- TARGET" if w==TARGET else ""
    print(f"{w}  mints_in_random={n}{tag}")
# overall most active snipers in random sample (to see scale of generic bots)
allcnt=Counter({w:len(ms) for w,ms in wallet_mints.items()})
print("\n=== most active snipers overall in random sample ===")
for w,n in allcnt.most_common(15):
    print(f"{w}  {n}")
json.dump({"nblocks":nblocks,"ndistinct_mints":ndistinct,"cohort_random_activity":res,
           "top_random_snipers":allcnt.most_common(30)},open("/root/caller/control2.json","w"),indent=1)
print("wrote control2.json",file=sys.stderr)
