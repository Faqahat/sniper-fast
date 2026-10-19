import os, json, time, sys, urllib.request, urllib.error, statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
RPC = "https://rpc-frankfurt.constant-k.com/?api-key=" + os.environ["CONSTANTK_TOKEN"]
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
CAP = 100; THRESH = 30
ALPH = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n = 0
    for c in s: n = n*58 + ALPH.index(c)
    full = n.to_bytes((n.bit_length()+7)//8, "big") if n else b""
    return b"\x00"*(len(s)-len(s.lstrip("1"))) + full
CREATE_DISC = bytes([24,30,200,40,5,28,7,119])

def rpc(m, p, tries=8):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode()
    for t in range(tries):
        try:
            req = urllib.request.Request(RPC, data=body, headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req, timeout=45) as r:
                j = json.loads(r.read())
            if "error" in j:
                time.sleep(0.3*(t+1)); continue
            return j.get("result")
        except urllib.error.HTTPError as e:
            time.sleep(1.0+0.8*t if getattr(e,"code",0)==429 else 0.4*(t+1))
        except Exception:
            time.sleep(0.4*(t+1))
    return None

def get_tx(sig):
    for v in (0,1,2):
        res = rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":v,"encoding":"jsonParsed"}])
        if res: return res
    return None

def full_keys(tx):
    msg = tx["transaction"]["message"]
    static = [k["pubkey"] if isinstance(k,dict) else k for k in msg.get("accountKeys",[])]
    la = tx.get("meta",{}).get("loadedAddresses") or {"writable":[],"readonly":[]}
    return msg, static + la.get("writable",[]) + la.get("readonly",[])

def create_user(tx):
    msg, keys = full_keys(tx)
    cand = []
    for ix in msg.get("instructions",[]):
        cand.append(ix)
    for inner in tx.get("meta",{}).get("innerInstructions",[]) or []:
        cand += inner.get("instructions",[])
    for ix in cand:
        pidx = ix.get("programIdIndex")
        prog = keys[pidx] if pidx is not None and pidx < len(keys) else ix.get("programId")
        if prog != PUMP: continue
        data = ix.get("data")
        if not data: continue
        try: raw = b58d(data)
        except Exception: continue
        if raw[:8] != CREATE_DISC: continue
        accs = ix.get("accounts",[])
        # accounts may be indices (list of int) or pubkeys depending on encoding
        if accs and isinstance(accs[0], int):
            accs = [keys[a] for a in accs if a < len(keys)]
        if len(accs) >= 8:
            return accs[7], keys[0], accs  # user (creator), fee payer, all
    return None, (keys[0] if keys else None), None

def prior(creator, before):
    r = rpc("getSignaturesForAddress", [creator, {"limit": CAP, "before": before}])
    return len(r) if r is not None else -1

res = json.load(open("/root/creators_resolved.json"))
exp = json.load(open("/root/expanded_raw.json"))
picks_mints = [m for m, c in res["picks"].items() if c]

def work(mint):
    cs = exp.get(mint,{}).get("create_sig")
    if not cs: return None
    tx = get_tx(cs)
    if not tx: return None
    user, feepayer, accs = create_user(tx)
    row = {"mint": mint, "feepayer": feepayer, "user": user}
    row["user_prior"] = prior(user, cs) if user else -2
    return row

rows = []
with ThreadPoolExecutor(max_workers=16) as ex:
    futs = {ex.submit(work, m): m for m in picks_mints}
    for f in as_completed(futs):
        r = f.result()
        if r: rows.append(r)

got_user = [r for r in rows if r["user"] and r["user_prior"] >= 0]
nouser = [r for r in rows if not r["user"]]
print(f"total picks probed: {len(rows)}  create-ix-user found: {len([r for r in rows if r['user']])}  no-user: {len(nouser)}")
# how often user == feepayer
same = sum(1 for r in rows if r["user"] and r["user"] == r["feepayer"])
print(f"user == feepayer in {same}/{len([r for r in rows if r['user']])}")
vals = sorted(r["user_prior"] for r in got_user)
if vals:
    print(f"USER (pump creator acct) prior-at-launch: measured={len(vals)} median={statistics.median(vals)} "
          f"p25={vals[len(vals)//4]} p75={vals[3*len(vals)//4]} p90={vals[min(len(vals)-1,int(0.9*len(vals)))]} max={max(vals)}")
    b = {"0":0,"1-5":0,"6-30":0,"31-99":0,"100+":0}
    for v in vals:
        if v==0: b["0"]+=1
        elif v<=5: b["1-5"]+=1
        elif v<=30: b["6-30"]+=1
        elif v<100: b["31-99"]+=1
        else: b["100+"]+=1
    print("USER buckets:", b)
    blocked = sum(1 for v in vals if v > THRESH)
    print(f"picks blocked by USER prior>{THRESH}: {blocked}/{len(vals)} = {100*blocked/len(vals):.1f}%")
json.dump(rows, open("/root/creator_acct_probe_out.json","w"))
