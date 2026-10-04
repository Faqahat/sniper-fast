#!/usr/bin/env python3
"""Trade size (SOL through the pool vaults) of every win >= MIN lamports in tmp-patterns/scan-*.json, via getTransaction (<= 3.5 req/s).
writes tmp-patterns/sizes.json {sig: size_sol}"""
import json, os, sys, glob, time, urllib.request, concurrent.futures as cf
os.chdir("/root/arb-lab")
MIN = int(sys.argv[1]) if len(sys.argv) > 1 else 10_000_000
WSOL = "So11111111111111111111111111111111111111112"
_env = dict(l.strip().split("=", 1) for l in open(".env") if "=" in l and not l.startswith("#"))
KEY = _env.get("HAAN_API_KEY", ""); del _env
out = "tmp-patterns/sizes.json"
S = json.load(open(out)) if os.path.exists(out) else {}
need = []
for f in sorted(glob.glob("tmp-patterns/scan-*.json")):
    for w in json.load(open(f))["wins"]:
        if w["gain"] >= MIN and w["sig"] not in S: need.append(w["sig"])
need = list(dict.fromkeys(need))
print("need", len(need), flush=True)
def rpc(m, p):
    for i in range(3):
        try:
            r = urllib.request.Request("https://rpc.haandigital.eu/", json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(),
                                       {"content-type": "application/json", "Authorization": "Bearer " + KEY})
            return json.load(urllib.request.urlopen(r, timeout=30)).get("result")
        except Exception: time.sleep(1 + i)
def size(sig):
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}])
    if not t: return None
    m = t["meta"]; signer = t["transaction"]["message"]["accountKeys"][0]
    pre = {b["accountIndex"]: b for b in m.get("preTokenBalances") or []}; post = {b["accountIndex"]: b for b in m.get("postTokenBalances") or []}
    best = 0
    for k in set(pre) | set(post):
        b = pre.get(k) or post.get(k)
        if b["mint"] != WSOL or b.get("owner") == signer: continue
        a1 = int((post.get(k) or {"uiTokenAmount": {"amount": "0"}})["uiTokenAmount"]["amount"]); a0 = int((pre.get(k) or {"uiTokenAmount": {"amount": "0"}})["uiTokenAmount"]["amount"])
        best = max(best, abs(a1 - a0))
    return {"size": best / 1e9, "cu": m.get("computeUnitsConsumed")}
t0 = time.time(); n = 0
with cf.ThreadPoolExecutor(3) as ex:
    for i in range(0, len(need), 3):
        batch = need[i:i + 3]
        for s, v in zip(batch, ex.map(size, batch)): S[s] = v
        n += len(batch)
        el = time.time() - t0
        if n / max(el, 1e-3) > 3.3: time.sleep(n / 3.3 - el)
        if n % 150 == 0: json.dump(S, open(out, "w")); print(n, round(time.time() - t0), flush=True)
json.dump(S, open(out, "w")); print("done", len(S), round(time.time() - t0), flush=True)
