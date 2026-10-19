import os, json, time, sys, urllib.request, urllib.error, statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
RPC = "https://rpc-frankfurt.constant-k.com/?api-key=" + os.environ["CONSTANTK_TOKEN"]
CAP = 100; THRESH = 30

def rpc(m, p, tries=8):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode()
    for t in range(tries):
        try:
            req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
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

# picks: mint -> creator, and expanded_raw: mint -> create_sig
res = json.load(open("/root/creators_resolved.json"))
exp = json.load(open("/root/expanded_raw.json"))
picks = {m: c for m, c in res["picks"].items() if c}

def prior(mc):
    mint, creator = mc
    cs = exp.get(mint, {}).get("create_sig")
    if not cs:
        return (mint, creator, -1)
    r = rpc("getSignaturesForAddress", [creator, {"limit": CAP, "before": cs}])
    if r is None:
        return (mint, creator, -1)
    return (mint, creator, len(r))

rows = []
with ThreadPoolExecutor(max_workers=20) as ex:
    futs = {ex.submit(prior, (m, c)): m for m, c in picks.items()}
    for f in as_completed(futs):
        rows.append(f.result())

vals = sorted(v for _, _, v in rows if v >= 0)
blocked_mints = sum(1 for _, _, v in rows if v > THRESH)
tot = sum(1 for _, _, v in rows if v >= 0)
print("PICKS point-in-time prior-at-launch sigs:")
print(f"  measured={tot} median={statistics.median(vals) if vals else None} "
      f"p25={vals[len(vals)//4] if vals else None} p75={vals[3*len(vals)//4] if vals else None} "
      f"p90={vals[min(len(vals)-1,int(0.9*len(vals)))] if vals else None} max={max(vals) if vals else None}")
b = {"0":0,"1-5":0,"6-30":0,"31-99":0,"100+":0}
for v in vals:
    if v==0: b["0"]+=1
    elif v<=5: b["1-5"]+=1
    elif v<=30: b["6-30"]+=1
    elif v<100: b["31-99"]+=1
    else: b["100+"]+=1
print("  buckets:", b)
print(f"  picks MINTS blocked (prior>{THRESH}): {blocked_mints}/{tot} = {100*blocked_mints/max(1,tot):.1f}%")
