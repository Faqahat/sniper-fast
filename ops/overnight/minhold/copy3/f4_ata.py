#!/usr/bin/env python3
# READ-ONLY RPC: for a wallet whose own address is flooded by other bots' txs (4vw54BmA), find all txs of each of its token
# accounts (taken from its own buy txs) -> the txs we have not fetched yet (e.g. PumpSwap sells after graduation) -> raw/<w8>_ata.jsonl.gz
import sys, os, json, gzip, time, urllib.request, concurrent.futures as cf
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
W = sys.argv[1]; W8 = W[:8]
def rpc(m, p, tries=8):
    for i in range(tries):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=60))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(0.5 * (i + 1))
WSOL = "So11111111111111111111111111111111111111112"
atas = {}; have = set()
for l in gzip.open(f"raw/{W8}.jsonl.gz", "rt"):
    t = json.loads(l); have.add(t["sig"])
    msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}; keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    for b in (t["meta"].get("postTokenBalances") or []) + (t["meta"].get("preTokenBalances") or []):
        if b.get("owner") == W and b["mint"] != WSOL: atas[keys[b["accountIndex"]]] = b["mint"]
print("token accounts", len(atas), flush=True)
def sigs(a):
    out = []; before = None
    while True:
        pg = rpc("getSignaturesForAddress", [a, {"limit": 1000, **({"before": before} if before else {})}]) or []
        out += pg
        if len(pg) < 1000: break
        before = pg[-1]["signature"]
    return a, out
new = {}
with cf.ThreadPoolExecutor(8) as ex:
    for a, pg in ex.map(sigs, list(atas)):
        for p in pg:
            if p["signature"] not in have and not p.get("err"): new[p["signature"]] = atas[a]
print("new successful txs on its token accounts", len(new), flush=True)
def one(s): return s, rpc("getTransaction", [s, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
n = 0
with gzip.open(f"raw/{W8}_ata.jsonl.gz", "wt") as fo, cf.ThreadPoolExecutor(8) as ex:
    for s, t in ex.map(one, list(new)):
        if t: t["sig"] = s; t["ata_mint"] = new[s]; fo.write(json.dumps(t, separators=(",", ":")) + "\n"); n += 1
print("done", n, flush=True)
