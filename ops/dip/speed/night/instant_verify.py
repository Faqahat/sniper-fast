import json, urllib.request, time
EP = "https://api.mainnet-beta.solana.com"
JITO = {"96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5","HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe","Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY","ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
        "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh","ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt","DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL","3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT"}
def rpc(m, p):
    for k in range(5):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(), headers={"content-type":"application/json"}), timeout=60))
            time.sleep(1.2)
            if "result" in r: return r["result"]
        except Exception: time.sleep(3)
def bundle(bid):
    return json.loads(urllib.request.urlopen(urllib.request.Request(f"https://bundles.jito.wtf/api/v1/bundles/bundle/{bid}", headers={"user-agent": "Mozilla/5.0"}), timeout=20).read())[0]
smp = [x for x in json.load(open("instant_sample.json")) if x["verdict"] == "SAME bundle"][:10]
for x in smp:
    b = bundle(x["dump_bundle"]); time.sleep(1.1)
    print(f"\n=== bundle {b['bundleId'][:12]} slot {b['slot']} txs {len(b['txSignatures'])} tippers {[t[:8] for t in b['tippers']]} tip {b['landedTipLamports']/1e9}")
    for s in b["txSignatures"]:
        t = rpc("getTransaction", [s, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])
        if not t: print("   (tx not found)", s[:10]); continue
        msg = t["transaction"]["message"]; keys = [k["pubkey"] for k in msg["accountKeys"]]
        signers = [k["pubkey"][:8] for k in msg["accountKeys"] if k.get("signer")]
        tips = [(i["parsed"]["info"]["source"][:8], i["parsed"]["info"]["lamports"] / 1e9) for i in msg["instructions"] if i.get("parsed", {}).get("type") == "transfer" and i["parsed"]["info"].get("destination") in JITO]
        progs = sorted({i.get("programId", "")[:6] for i in msg["instructions"]})
        logs = " ".join(t["meta"].get("logMessages") or [])
        kind = "SELL" if "Instruction: Sell" in logs else ("BUY" if "Instruction: Buy" in logs else "other")
        print(f"   {s[:10]} signers {signers} | {kind} | jito tips in tx {tips} | programs {progs}")
