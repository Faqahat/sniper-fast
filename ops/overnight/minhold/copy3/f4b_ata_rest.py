#!/usr/bin/env python3
# READ-ONLY RPC: salvage the partial raw/4vw54BmA_ata.jsonl.gz (timed out) into raw/4vw54BmA_ata_a.jsonl.gz, then fetch the remaining
# txs of the token accounts of 4vw54's OPEN (graduated) positions only -> raw/4vw54BmA_ata_b.jsonl.gz
import sys, os, json, gzip, time, urllib.request, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib3
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
W = lib3.W3["4vw54BmA"]; WSOL = "So11111111111111111111111111111111111111112"
def rpc(m, p, tries=8):
    for i in range(tries):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=60))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(0.5 * (i + 1))
have = set()
with gzip.open("raw/4vw54BmA_ata_a.jsonl.gz", "wt") as fo:
    try:
        for l in gzip.open("raw/4vw54BmA_ata.jsonl.gz", "rt"):
            try: t = json.loads(l)
            except Exception: continue
            have.add(t["sig"]); fo.write(l if l.endswith("\n") else l + "\n")
    except (EOFError, OSError): pass
for l in gzip.open("raw/4vw54BmA.jsonl.gz", "rt"): have.add(json.loads(l)["sig"])
P = [p for p in json.load(open("out/pos3.json")) if p["w"] == "4vw54BmA" and not p.get("nobuy") and p["open"]]
openm = {p["m"] for p in P}
atas = {}
for l in gzip.open("raw/4vw54BmA.jsonl.gz", "rt"):
    t = json.loads(l); msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}; keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    for b in (t["meta"].get("postTokenBalances") or []) + (t["meta"].get("preTokenBalances") or []):
        if b.get("owner") == W and b["mint"] in openm: atas[keys[b["accountIndex"]]] = b["mint"]
print("salvaged", len(have), "open-position token accounts", len(atas), flush=True)
new = {}
for a, m in atas.items():
    before = None
    while True:
        pg = rpc("getSignaturesForAddress", [a, {"limit": 1000, **({"before": before} if before else {})}]) or []
        for p in pg:
            if p["signature"] not in have and not p.get("err"): new[p["signature"]] = m
        if len(pg) < 1000: break
        before = pg[-1]["signature"]
print("to fetch", len(new), flush=True)
def one(s): return s, rpc("getTransaction", [s, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
n = 0
with gzip.open("raw/4vw54BmA_ata_b.jsonl.gz", "wt") as fo, cf.ThreadPoolExecutor(12) as ex:
    for s, t in ex.map(one, list(new)):
        if t: t["sig"] = s; t["ata_mint"] = new[s]; fo.write(json.dumps(t, separators=(",", ":")) + "\n"); n += 1
print("done", n, flush=True)
