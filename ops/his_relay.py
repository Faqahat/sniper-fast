import json, urllib.request, os, time, concurrent.futures as cf
from collections import Counter
TOK = os.environ["CONSTANTK_TOKEN"]
RPC = f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
W = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
SYS = "11111111111111111111111111111111"

# known relay tip accounts / prefixes
JITO = {"96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5", "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
        "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY", "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
        "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh", "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
        "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL", "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT"}
HELIUS = {"4ACfpUFoaSD9bfPdeu6DBt89gB6ENTeHBXCAi87NhDEE", "D2L6yPZ2FmmmTKPgzaMKdhu6EWZcTpLy1Vhx8uvZe7NZ",
          "9bnz4RShgq1hAnLnZbP8kbgBg1kEmcJBYQq3gQbmnSta", "5VY91ws6B2hMmBFRsXkoAAdsPHBJwRfBht4DXox3xkwn"}


def rpc(m, p):
    req = urllib.request.Request(RPC, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"})
    for i in range(5):
        try:
            return json.load(urllib.request.urlopen(req, timeout=20)).get("result")
        except Exception:
            time.sleep(0.3 * (i + 1))
    return None


def relay_of(sig):
    tx = rpc("getTransaction", [sig, {"maxSupportedTransactionVersion": 0, "encoding": "jsonParsed"}])
    if not tx or not tx.get("meta") or tx["meta"].get("err"):
        return None
    logs = tx["meta"].get("logMessages", [])
    if not any("Instruction: Buy" in l for l in logs):
        return None  # only buys
    ixs = list(tx["transaction"]["message"].get("instructions", []))
    for inner in tx["meta"].get("innerInstructions", []):
        ixs += inner["instructions"]
    tips = []
    for ix in ixs:
        pj = ix.get("parsed")
        if ix.get("program") == "system" and isinstance(pj, dict) and pj.get("type") == "transfer":
            dst = pj["info"].get("destination", "")
            lam = int(pj["info"].get("lamports", 0))
            if dst == W:
                continue
            tips.append((dst, lam))
    # classify
    rel = "direct/no-tip"
    for dst, lam in tips:
        if dst.startswith("moon"):
            rel = f"LunarLander(moon) tip={lam/1e9:.4f}"
        elif dst.startswith("noz") or dst.lower().startswith("noz"):
            rel = f"Nozomi(noz) tip={lam/1e9:.4f}"
        elif dst in JITO:
            rel = f"Jito tip={lam/1e9:.4f}"
        elif dst in HELIUS or dst.startswith("4ACf"):
            rel = f"Helius tip={lam/1e9:.4f}"
        elif dst.lower().startswith("astr") or dst.startswith("AStR"):
            rel = f"Astralane tip={lam/1e9:.4f}"
        elif dst.startswith("rapid"):
            rel = f"rapid tip={lam/1e9:.4f}"
        elif lam >= 500000:  # a non-fee tip to an unknown dst
            rel = f"other-tip dst={dst[:8]} tip={lam/1e9:.4f}"
    return rel


sigs = rpc("getSignaturesForAddress", [W, {"limit": 120}]) or []
sl = [s["signature"] for s in sigs]
rels = []
with cf.ThreadPoolExecutor(max_workers=10) as ex:
    for r in ex.map(relay_of, sl):
        if r:
            rels.append(r)
# collapse to relay name (strip tip value for the counter)
names = Counter(r.split(" tip=")[0].split(" dst=")[0] for r in rels)
print(f"4yFAz recent BUYS analyzed: {len(rels)}")
print("relay/send-path distribution:")
for name, c in names.most_common():
    print(f"  {name}: {c} ({c/len(rels)*100:.0f}%)")
print("\nsample tip sizes:")
for r in rels[:15]:
    print("  ", r)
