import os, json, time, sys, urllib.request, urllib.error, statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
RPC = "https://rpc-frankfurt.constant-k.com/?api-key=" + os.environ["CONSTANTK_TOKEN"]
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
CAP = 100; THRESH = 30
CREATE_DISCS = {"181ec828051c0777", "07051dc4f5176550"}
CREATOR_IDX = 7
ALPH = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n = 0
    for c in s: n = n*58 + ALPH.index(c)
    full = n.to_bytes((n.bit_length()+7)//8, "big") if n else b""
    return b"\x00"*(len(s)-len(s.lstrip("1"))) + full

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
        r = rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":v,"encoding":"jsonParsed"}])
        if r: return r
    return None

def full_keys(tx):
    msg = tx["transaction"]["message"]
    static = [k["pubkey"] if isinstance(k,dict) else k for k in msg.get("accountKeys",[])]
    la = tx.get("meta",{}).get("loadedAddresses") or {"writable":[],"readonly":[]}
    return msg, static + la.get("writable",[]) + la.get("readonly",[])

def create_creator(tx):
    """return creator pubkey (pump create ix account[7]) or None"""
    msg, keys = full_keys(tx)
    ixs = list(msg.get("instructions",[]))
    for inner in tx.get("meta",{}).get("innerInstructions",[]) or []:
        ixs += inner.get("instructions",[])
    for ix in ixs:
        pidx = ix.get("programIdIndex")
        prog = keys[pidx] if (pidx is not None and pidx < len(keys)) else ix.get("programId")
        if prog != PUMP: continue
        data = ix.get("data")
        if not data: continue
        try: disc = b58d(data)[:8].hex()
        except Exception: continue
        if disc not in CREATE_DISCS: continue
        accs = ix.get("accounts",[])
        if accs and isinstance(accs[0], int):
            accs = [keys[a] if a < len(keys) else None for a in accs]
        if len(accs) > CREATOR_IDX:
            return accs[CREATOR_IDX]
    return None

def oldest_sig(mint):
    r = rpc("getSignaturesForAddress",[mint,{"limit":1000}])
    if not r: return None
    if len(r) >= 1000:
        before = r[-1]["signature"]; pages = 1
        while pages < 6:
            r2 = rpc("getSignaturesForAddress",[mint,{"limit":1000,"before":before}])
            if not r2: break
            before = r2[-1]["signature"]; pages += 1
            if len(r2) < 1000: r = r2; break
        else:
            return None
    return r[-1]["signature"]

def prior(creator, before):
    r = rpc("getSignaturesForAddress",[creator,{"limit":CAP,"before":before}])
    return len(r) if r is not None else -1

# ---------- PICKS ----------
res = json.load(open("/root/creators_resolved.json"))
exp = json.load(open("/root/expanded_raw.json"))
pick_mints = list(res["picks"].keys())

def pick_work(mint):
    cs = exp.get(mint,{}).get("create_sig")
    if not cs: return (mint, None, None, -3)
    tx = get_tx(cs)
    if not tx: return (mint, None, cs, -3)
    cr = create_creator(tx)
    if not cr: return (mint, None, cs, -2)
    return (mint, cr, cs, prior(cr, cs))

pick_rows = {}
with ThreadPoolExecutor(max_workers=16) as ex:
    futs = {ex.submit(pick_work, m): m for m in pick_mints}
    done = 0
    for f in as_completed(futs):
        m, cr, cs, pr = f.result(); pick_rows[m] = {"creator":cr,"create_sig":cs,"prior":pr}; done += 1
        if done % 100 == 0: print(f"  picks {done}/{len(pick_mints)}", file=sys.stderr)
print("picks done", file=sys.stderr)

# ---------- POPULATION ----------
pop_mints = list(res["pop"].keys())
def pop_work(mint):
    cs = oldest_sig(mint)
    if not cs: return (mint, None, None, -3)
    tx = get_tx(cs)
    if not tx: return (mint, None, cs, -3)
    cr = create_creator(tx)
    if not cr: return (mint, None, cs, -2)
    return (mint, cr, cs, prior(cr, cs))

pop_rows = {}
with ThreadPoolExecutor(max_workers=24) as ex:
    futs = {ex.submit(pop_work, m): m for m in pop_mints}
    done = 0
    for f in as_completed(futs):
        m, cr, cs, pr = f.result(); pop_rows[m] = {"creator":cr,"create_sig":cs,"prior":pr}; done += 1
        if done % 250 == 0: print(f"  pop {done}/{len(pop_mints)}", file=sys.stderr)
print("pop done", file=sys.stderr)

json.dump({"picks":pick_rows,"pop":pop_rows}, open("/root/creator_pit.json","w"))

# ---------- BLOCKLIST (population serial creators) ----------
# per-creator max prior-at-launch observed; block if > THRESH
pop_creator_prior = {}
for m, r in pop_rows.items():
    cr = r["creator"]; pr = r["prior"]
    if cr and pr >= 0:
        pop_creator_prior[cr] = max(pop_creator_prior.get(cr, -1), pr)
blocked = sorted(c for c, pr in pop_creator_prior.items() if pr > THRESH)
with open("/root/arbx-fast/creator_blocklist.txt","w") as f:
    for c in blocked: f.write(c+"\n")

# ---------- REPORT ----------
def dist(vals, label):
    vals = sorted(vals)
    if not vals:
        print(f"{label}: EMPTY"); return
    def q(x): return vals[min(len(vals)-1, int(x*len(vals)))]
    b = {"0":0,"1-5":0,"6-30":0,"31-99":0,"100+(cap)":0}
    for v in vals:
        if v==0: b["0"]+=1
        elif v<=5: b["1-5"]+=1
        elif v<=30: b["6-30"]+=1
        elif v<100: b["31-99"]+=1
        else: b["100+(cap)"]+=1
    print(f"{label}: n={len(vals)} median={statistics.median(vals)} p25={q(.25)} p75={q(.75)} p90={q(.9)} p99={q(.99)} max={max(vals)}")
    print(f"   buckets={b}")

pop_prior_vals = [r["prior"] for r in pop_rows.values() if r["prior"] >= 0]
print("==== POPULATION creators (pump create ix acct[7]) prior-at-launch ====")
dist(pop_prior_vals, "pop")
print(f"unique pop creators measured: {len(pop_creator_prior)}")
print(f"pop creators blocklisted (max prior > {THRESH}): {len(blocked)}")
print(f"blocklist file: /root/arbx-fast/creator_blocklist.txt lines={len(blocked)}")

# validation
pick_prior_vals = [r["prior"] for r in pick_rows.values() if r["prior"] >= 0]
print("==== VALIDATION vs 4yFAz picks (creator = create ix acct[7]) ====")
dist(pick_prior_vals, "picks")
blockset = set(blocked)
# unique pick creators
pick_creator_prior = {}
for m, r in pick_rows.items():
    cr = r["creator"]; pr = r["prior"]
    if cr and pr >= 0:
        pick_creator_prior.setdefault(cr, []).append(pr)
pc_block_bylist = sum(1 for c in pick_creator_prior if c in blockset)
pc_block_bythresh = sum(1 for c, prs in pick_creator_prior.items() if max(prs) > THRESH)
mint_block_bythresh = sum(1 for m, r in pick_rows.items() if r["creator"] and r["prior"] > THRESH)
mint_measured = sum(1 for m, r in pick_rows.items() if r["creator"] and r["prior"] >= 0)
print(f"pick unique creators measured: {len(pick_creator_prior)}")
print(f"  blocked by threshold(prior>{THRESH}): {pc_block_bythresh}/{len(pick_creator_prior)} = {100*pc_block_bythresh/max(1,len(pick_creator_prior)):.1f}%")
print(f"  present in population blocklist: {pc_block_bylist}/{len(pick_creator_prior)} = {100*pc_block_bylist/max(1,len(pick_creator_prior)):.1f}%")
print(f"pick MINTS blocked by threshold: {mint_block_bythresh}/{mint_measured} = {100*mint_block_bythresh/max(1,mint_measured):.1f}%")
# resolution health
print("resolve fail picks:", {k: sum(1 for r in pick_rows.values() if r['prior']==k) for k in (-2,-3)})
print("resolve fail pop:", {k: sum(1 for r in pop_rows.values() if r['prior']==k) for k in (-2,-3)})
