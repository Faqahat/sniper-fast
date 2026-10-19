import os, json, time, sys, urllib.request, urllib.error, statistics, struct
from concurrent.futures import ThreadPoolExecutor, as_completed
RPC = "https://rpc-frankfurt.constant-k.com/?api-key=" + os.environ["CONSTANTK_TOKEN"]
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
CREATE_V2 = "d6904cec5f8b31b4"; CREATE = "181ec828051c0777"
CAP = 100; THRESH = 30
B58A = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n = 0
    for c in s: n = n*58 + B58A.index(c)
    full = n.to_bytes((n.bit_length()+7)//8, "big") if n else b""
    return b"\x00"*(len(s)-len(s.lstrip("1"))) + full
def b58e(bb):
    n = int.from_bytes(bb, "big"); out = ""
    while n: n, r = divmod(n, 58); out = B58A[r] + out
    pad = len(bb) - len(bb.lstrip(b"\x00"))
    return "1"*pad + out
def rpc(m, p, tries=8):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode()
    for t in range(tries):
        try:
            req = urllib.request.Request(RPC, data=body, headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req, timeout=45) as r: j = json.loads(r.read())
            if "error" in j: time.sleep(0.3*(t+1)); continue
            return j.get("result")
        except urllib.error.HTTPError as e:
            time.sleep(1.0+0.8*t if getattr(e,"code",0)==429 else 0.4*(t+1))
        except Exception: time.sleep(0.4*(t+1))
    return None
def get_tx(sig):
    for v in (0,1,2):
        r = rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":v,"encoding":"jsonParsed"}])
        if r: return r
    return None
def arg_creator(tx):
    msg = tx["transaction"]["message"]
    static = [k["pubkey"] if isinstance(k,dict) else k for k in msg.get("accountKeys",[])]
    la = tx.get("meta",{}).get("loadedAddresses") or {"writable":[],"readonly":[]}
    keys = static + la.get("writable",[]) + la.get("readonly",[])
    ixs = list(msg.get("instructions",[]))
    for inner in tx.get("meta",{}).get("innerInstructions",[]) or []:
        ixs += inner.get("instructions",[])
    create = None
    for ix in ixs:
        pidx = ix.get("programIdIndex")
        prog = keys[pidx] if (pidx is not None and pidx < len(keys)) else ix.get("programId")
        if prog != PUMP: continue
        d = ix.get("data")
        if not d: continue
        try: raw = b58d(d)
        except Exception: continue
        h = raw[:8].hex()
        if h == CREATE_V2: create = raw; break
        if h == CREATE and create is None: create = raw
    if not create: return None
    data = create; p = 8
    for _ in range(3):
        if p+4 > len(data): return None
        ln = struct.unpack("<I", data[p:p+4])[0]; p += 4 + ln
    if p+32 > len(data): return None
    return b58e(data[p:p+32])
def total_sigs(c):
    r = rpc("getSignaturesForAddress",[c,{"limit":CAP}])
    return len(r) if r is not None else -1
def prior_sigs(c, before):
    r = rpc("getSignaturesForAddress",[c,{"limit":CAP,"before":before}])
    return len(r) if r is not None else -1

res = json.load(open("/root/creators_resolved.json"))
exp = json.load(open("/root/expanded_raw.json"))
mode = sys.argv[1] if len(sys.argv) > 1 else "picks"
if mode == "picks":
    items = [(m, exp.get(m,{}).get("create_sig")) for m in res["picks"].keys()]
else:
    pit = json.load(open("/root/creator_pit.json"))  # has create_sig per pop mint (oldest)
    items = [(m, pit["pop"][m].get("create_sig")) for m in pit["pop"].keys()]
def work(mc):
    mint, cs = mc
    if not cs: return (mint, None, None, -3, -3)
    tx = get_tx(cs)
    if not tx: return (mint, None, cs, -3, -3)
    cr = arg_creator(tx)
    if not cr: return (mint, None, cs, -2, -2)
    return (mint, cr, cs, total_sigs(cr), prior_sigs(cr, cs))
rows = {}
with ThreadPoolExecutor(max_workers=20) as ex:
    futs = {ex.submit(work, it): it for it in items}
    done = 0
    for f in as_completed(futs):
        m, cr, cs, tot, pr = f.result(); rows[m] = {"creator":cr,"create_sig":cs,"total":tot,"prior":pr}; done += 1
        if done % 200 == 0: print(f"  {done}/{len(items)}", file=sys.stderr)
json.dump(rows, open(f"/root/argcreator_{mode}.json","w"))
def dist(vals, label):
    vals = sorted(v for v in vals if v >= 0)
    if not vals: print(f"{label}: EMPTY"); return
    def q(x): return vals[min(len(vals)-1,int(x*len(vals)))]
    b={"0":0,"1-5":0,"6-30":0,"31-99":0,"100cap":0}
    for v in vals:
        if v==0:b["0"]+=1
        elif v<=5:b["1-5"]+=1
        elif v<=30:b["6-30"]+=1
        elif v<100:b["31-99"]+=1
        else:b["100cap"]+=1
    print(f"{label}: n={len(vals)} median={statistics.median(vals)} p25={q(.25)} p75={q(.75)} p90={q(.9)} max={max(vals)} {b}")
resolved = sum(1 for r in rows.values() if r["creator"])
fail2 = sum(1 for r in rows.values() if r["total"]==-2)
fail3 = sum(1 for r in rows.values() if r["total"]==-3)
print(f"[{mode}] items={len(items)} arg-creator resolved={resolved} no-create-ix={fail2} no-tx={fail3}")
dist([r["total"] for r in rows.values() if r["creator"]], f"[{mode}] TOTAL lifetime sigs")
dist([r["prior"] for r in rows.values() if r["creator"]], f"[{mode}] PRIOR-at-launch sigs")
tot_block = sum(1 for r in rows.values() if r["creator"] and r["total"]>THRESH)
tot_meas  = sum(1 for r in rows.values() if r["creator"] and r["total"]>=0)
pri_block = sum(1 for r in rows.values() if r["creator"] and r["prior"]>THRESH)
pri_meas  = sum(1 for r in rows.values() if r["creator"] and r["prior"]>=0)
print(f"[{mode}] blocked by TOTAL>{THRESH}: {tot_block}/{tot_meas} = {100*tot_block/max(1,tot_meas):.1f}%")
print(f"[{mode}] blocked by PRIOR>{THRESH}: {pri_block}/{pri_meas} = {100*pri_block/max(1,pri_meas):.1f}%")
