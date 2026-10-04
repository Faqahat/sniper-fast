#!/usr/bin/env python3
"""Which pools do the DAMM v2 winners trade? getTransaction of sampled wins; every venue instruction (top-level and
inner) gives its pool: DAMM v2 swap accounts[1], PumpSwap accounts[0], DLMM accounts[0], Raydium CPMM accounts[3],
AMMv4 accounts[1]. Output runs/damm-pools.json: pool counts per venue and DAMM v2 <-> other pool pairs."""
import json, urllib.request, collections, time, os, concurrent.futures as cf
os.chdir("/root/arb-lab")
env = dict(l.strip().split("=", 1) for l in open(".env") if "=" in l and not l.startswith("#"))
U = env["RMR_RPC_URL"]
V = {"cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG": ("DAMMv2", 1), "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA": ("PumpSwap", 0),
     "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo": ("DLMM", 0), "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C": ("RayCPMM", 3),
     "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": ("RayAMMv4", 1)}
def tx(s):
    for i in range(3):
        try:
            r = urllib.request.Request(U, json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getTransaction", "params": [s, {"encoding": "json", "maxSupportedTransactionVersion": 1}]}).encode(), {"content-type": "application/json"})
            return json.load(urllib.request.urlopen(r, timeout=30)).get("result")
        except Exception: time.sleep(1 + i)
def pools(s):
    t = tx(s)
    if not t or t["meta"]["err"]: return None
    m = t["transaction"]["message"]
    keys = m["accountKeys"] + t["meta"].get("loadedAddresses", {}).get("writable", []) + t["meta"].get("loadedAddresses", {}).get("readonly", [])
    out = set()
    ixs = list(m["instructions"]) + [ix for g in t["meta"].get("innerInstructions") or [] for ix in g["instructions"]]
    for ix in ixs:
        p = keys[ix["programIdIndex"]]
        if p in V and len(ix["accounts"]) > V[p][1] + 2:
            out.add((V[p][0], keys[ix["accounts"][V[p][1]]]))
    return sorted(out)
sigs = json.load(open("runs/damm-win-sigs.json"))
cnt = collections.Counter(); pairs = collections.Counter()
with cf.ThreadPoolExecutor(8) as ex:
    for r in ex.map(pools, sigs):
        if not r: continue
        for x in r: cnt[x] += 1
        d = [p for v, p in r if v == "DAMMv2"]
        for v, p in r:
            if v != "DAMMv2":
                for q in d: pairs[(q, v, p)] += 1
json.dump({"pools": [[v, p, n] for (v, p), n in cnt.most_common()], "pairs": [[d, v, p, n] for (d, v, p), n in pairs.most_common()]}, open("runs/damm-pools.json", "w"))
print("pools by venue:", collections.Counter(v for v, p in cnt).most_common(), "distinct DAMMv2 pools", sum(1 for v, p in cnt if v == "DAMMv2"))
print("top pairs:", [(d[:6], v, p[:6], n) for (d, v, p), n in pairs.most_common(10)])
