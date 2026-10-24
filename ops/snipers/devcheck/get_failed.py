#!/usr/bin/env python3
# READ-ONLY: failed txs of a wallet (owner-RPC window only) -> the pump.fun mint each one tried to buy (account key ending in "pump").
# usage: get_failed.py <ledger.json> <cachedir> <out.json>
import sys, os, json, time, urllib.request, concurrent.futures as cf
LED, CACHE, OUT = sys.argv[1:4]; os.makedirs(CACHE, exist_ok=True)
CK = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
def rpc(m, p, tries=8):
    for i in range(tries):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(CK, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=30))
            if "error" in r: raise RuntimeError(str(r["error"])[:200])
            return r["result"]
        except Exception as e: err = e; time.sleep(min(8, 0.5 * 2 ** i))
    raise RuntimeError(f"{m}: {err}")
MIN = rpc("minimumLedgerSlot", []) + 60000
D = json.load(open(LED))
bought = {t["mint"] for x in D["txs"] if not x.get("err") for t in x.get("trades") or [] if t["buy"]}
E = [x for x in D["txs"] if x.get("err") and x["slot"] > MIN]
def one(x):
    p = os.path.join(CACHE, x["sig"] + ".json")
    if os.path.exists(p): return x, json.load(open(p))
    t = rpc("getTransaction", [x["sig"], {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    if t: json.dump(t, open(p, "w"))
    return x, t
att = {}
with cf.ThreadPoolExecutor(8) as ex:
    for x, t in ex.map(one, E):
        if not t: continue
        keys = [k["pubkey"] if isinstance(k, dict) else k for k in t["transaction"]["message"]["accountKeys"]]
        pm = [k for k in keys if k.endswith("pump")]
        lg = " ".join(t["meta"].get("logMessages") or [])
        if pm and "Buy" in lg and pm[0] not in bought and pm[0] not in att: att[pm[0]] = dict(sig=x["sig"], slot=x["slot"], bt=x["bt"])
json.dump(att, open(OUT, "w"))
print(f"{D['wallet'][:8]}: failed txs in window {len(E)}; failed BUY attempts on {len(att)} never-bought launches", flush=True)
