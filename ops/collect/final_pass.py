#!/usr/bin/env python3
# READ-ONLY final snapshot for a finished collect.py run: every launch's bonding-curve account (getMultipleAccounts, 100
# per call) + top token holders (getTokenLargestAccounts). Appends to OUT/final.jsonl, skipping mints already there.
# Endpoints: RMR_RPC_URL (main) + Constant-K (capped at its "veryheavy" 2/s); URLs never printed.
import os, json, time, threading, urllib.request, urllib.error, collections
from concurrent.futures import ThreadPoolExecutor
OUT = os.environ["OUT"]
EPS = [(os.environ["RMR_RPC_URL"], float(os.environ.get("RMR_RPS", "15"))),
       ("https://rpc-frankfurt.constant-k.com/?api-key=" + os.environ["CONSTANTK_TOKEN"], 1.8)]
locks = [threading.Lock() for _ in EPS]; nxt = [0.0 for _ in EPS]; ST = collections.Counter(); rr = [0]
def rpc(m, p):
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode()
    for k in range(12):
        with locks[0]: rr[0] += 1; e = 0 if (rr[0] % 9) else 1          # ~1 in 9 calls to Constant-K
        with locks[e]:
            t = max(time.time(), nxt[e]); nxt[e] = t + 1.0 / EPS[e][1]
        if t > time.time(): time.sleep(t - time.time())
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EPS[e][0], data=data, headers={"content-type": "application/json"}), timeout=30))
            if "error" in r: ST[f"err{e}"] += 1; time.sleep(min(10, 0.5 * (k + 1))); continue
            ST[f"ok{e}"] += 1; return r.get("result")
        except urllib.error.HTTPError as x: ST[f"http{x.code}_{e}"] += 1; time.sleep(min(10, 0.5 * (k + 1)))
        except Exception: ST[f"exc{e}"] += 1; time.sleep(min(10, 0.5 * (k + 1)))
    ST["gave_up"] += 1; return None
L = {}
for l in open(os.path.join(OUT, "launches.jsonl")):
    try: c = json.loads(l); L[c["mint"]] = c.get("bonding_curve")
    except Exception: pass
done = set()
if os.path.exists(os.path.join(OUT, "final.jsonl")):
    for l in open(os.path.join(OUT, "final.jsonl")):
        try:
            r = json.loads(l)
            if r.get("top_holders") is not None and r.get("curve") is not None: done.add(r["mint"])   # retry rows that came back empty
        except Exception: pass
todo = [m for m in L if m not in done and L[m]]
print(f"launches {len(L)}, already snapshotted {len(done)}, to do {len(todo)}", flush=True)
wl = threading.Lock(); f = open(os.path.join(OUT, "final.jsonl"), "a"); n = [0]; t0 = time.time()
def batch(part):
    acc = rpc("getMultipleAccounts", [[L[m] for m in part], {"encoding": "base64"}]) or {}
    vals = (acc or {}).get("value") or [None] * len(part)
    for m, a in zip(part, vals):
        hold = rpc("getTokenLargestAccounts", [m])
        with wl:
            f.write(json.dumps(dict(mint=m, t=time.time(), curve=a, top_holders=(hold or {}).get("value")), separators=(",", ":")) + "\n"); n[0] += 1
            if n[0] % 1000 == 0:
                f.flush(); print(f"{n[0]}/{len(todo)} in {time.time() - t0:.0f}s {dict(ST)}", flush=True)
with ThreadPoolExecutor(int(os.environ.get("THREADS", "12"))) as ex:
    list(ex.map(batch, [todo[k:k + 100] for k in range(0, len(todo), 100)]))
f.close()
json.dump(dict(phase="FINAL DONE", snapshotted=len(done) + n[0], launches=len(L), now=time.time(), stats=dict(ST)), open(os.path.join(OUT, "final_status.json"), "w"))
print("FINAL DONE", n[0], dict(ST), flush=True)
