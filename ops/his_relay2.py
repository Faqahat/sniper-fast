import json, urllib.request, os, time, concurrent.futures as cf
from collections import Counter
TOK = os.environ["CONSTANTK_TOKEN"]
RPC = f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
W = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
JITO = {"96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5", "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
        "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY", "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
        "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh", "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
        "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL", "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT"}


def rpc(m, p):
    req = urllib.request.Request(RPC, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"})
    for i in range(5):
        try:
            return json.load(urllib.request.urlopen(req, timeout=20)).get("result")
        except Exception:
            time.sleep(0.3 * (i + 1))
    return None


def small_tips(sig):
    tx = rpc("getTransaction", [sig, {"maxSupportedTransactionVersion": 0, "encoding": "jsonParsed"}])
    if not tx or not tx.get("meta") or tx["meta"].get("err"):
        return None
    logs = tx["meta"].get("logMessages", [])
    if not any("Instruction: Buy" in l for l in logs):
        return None
    ixs = list(tx["transaction"]["message"].get("instructions", []))
    for inner in tx["meta"].get("innerInstructions", []):
        ixs += inner["instructions"]
    # which programs are in the tx (detect Jito/relay by program or tip)
    progs = set()
    for ix in ixs:
        if "programId" in ix:
            progs.add(ix["programId"])
    found = []
    for ix in ixs:
        pj = ix.get("parsed")
        if ix.get("program") == "system" and isinstance(pj, dict) and pj.get("type") == "transfer":
            dst = pj["info"].get("destination", "")
            lam = int(pj["info"].get("lamports", 0))
            if dst == W:
                continue
            if 100000 <= lam <= 30000000:  # 0.0001 - 0.03 SOL = plausible relay tip
                found.append((dst, lam))
    return (found, progs)


sigs = rpc("getSignaturesForAddress", [W, {"limit": 120}]) or []
sl = [s["signature"] for s in sigs]
tipdsts = Counter()
tipsizes = []
jito_hits = 0
n = 0
with cf.ThreadPoolExecutor(max_workers=10) as ex:
    for res in ex.map(small_tips, sl):
        if res is None:
            continue
        found, progs = res
        n += 1
        if any(j in progs for j in []) or (progs & JITO):
            jito_hits += 1
        for dst, lam in found:
            tag = "JITO" if dst in JITO else ("moon-LunarLander" if dst.startswith("moon") else ("noz-Nozomi" if dst.startswith("noz") else ("Helius" if dst.startswith("4ACf") else dst[:8])))
            tipdsts[tag] += 1
            tipsizes.append(lam / 1e9)
print(f"4yFAz buys analyzed: {n}")
print(f"buys with a small tip (0.0001-0.03 SOL): {sum(tipdsts.values())}")
print("tip destinations (relay fingerprint):")
for dst, c in tipdsts.most_common(15):
    print(f"  {dst}: {c}")
if tipsizes:
    import statistics
    print(f"tip sizes: median {statistics.median(tipsizes):.4f} SOL  range {min(tipsizes):.4f}-{max(tipsizes):.4f}")
else:
    print("NO small relay-style tips found -> he likely sends DIRECT (staked, no relay tip)")
