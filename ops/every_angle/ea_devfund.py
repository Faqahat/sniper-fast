import json, sys, threading
import concurrent.futures as cf
sys.path.insert(0,'/root/last30')
import rpc
SYS="11111111111111111111111111111111"

def oldest_sigs(addr, maxpages=12):
    out=[]; before=None; pages=0
    while pages<maxpages:
        o={"limit":1000}
        if before: o["before"]=before
        page=rpc.call("getSignaturesForAddress",[addr,o])
        if not page: break
        out+=page; pages+=1
        if len(page)<1000: break
        before=page[-1]["signature"]
    return out  # newest-first overall

def funder_of(addr):
    """find who sent the first SOL to this wallet (1 hop). returns (funder, lamports, sig)."""
    sigs=oldest_sigs(addr)
    if not sigs: return None
    sigs=sorted(sigs, key=lambda s:(s.get("slot") or 0))  # oldest first
    # scan earliest txs for a SOL credit to addr
    for s in sigs[:6]:
        if s.get("err"): continue
        tx=rpc.gettx(s["signature"])
        if not tx: continue
        meta=tx.get("meta") or {}
        msg=tx["transaction"]["message"]
        keys=[k["pubkey"] if isinstance(k,dict) else k for k in msg["accountKeys"]]
        try: ai=keys.index(addr)
        except ValueError: continue
        delta=meta["postBalances"][ai]-meta["preBalances"][ai]
        if delta<=0: continue
        # funder = signer (fee payer) that lost SOL, most likely keys[0]
        funder=keys[0]
        if funder==addr:
            # addr paid itself; find another account that decreased
            cand=[(keys[i],meta["preBalances"][i]-meta["postBalances"][i]) for i in range(len(keys)) if keys[i]!=addr]
            cand=[c for c in cand if c[1]>0]
            if cand: funder=max(cand,key=lambda c:c[1])[0]
        return {"funder":funder,"lamports":delta,"sig":s["signature"],"slot":s.get("slot")}
    return None

tape=json.load(open('/root/mirror/his_tape.json'))
creators=sorted(set(d['creator'] for d in tape if d.get('creator')))
print(f"{len(creators)} distinct creators", file=sys.stderr)
out={}; lock=threading.Lock(); done=[0]
def work(c):
    try: f=funder_of(c)
    except Exception as e: f={"error":str(e)}
    with lock:
        done[0]+=1
        if done[0]%20==0: print(f"  {done[0]}/{len(creators)}", file=sys.stderr)
    return c, f
with cf.ThreadPoolExecutor(max_workers=6) as ex:
    for c, f in ex.map(work, creators):
        out[c]=f
json.dump(out, open('/root/every_angle/devfund.json','w'))
# quick cluster print
from collections import Counter
fc=Counter(v["funder"] for v in out.values() if v and "funder" in v)
print("top funders:", file=sys.stderr)
for k,n in fc.most_common(15): print(f"  {n:3d}  {k}", file=sys.stderr)
