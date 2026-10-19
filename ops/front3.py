import json, urllib.request, os, time, concurrent.futures as cf
TOK = os.environ["CONSTANTK_TOKEN"]
RPC = f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
MINT = "JE9LHzWe2ovReNuxPBfxvfAci18gr54nRpcsGLG6pump"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
CB = "ComputeBudget111111111111111111111111111111"
WSOL = "So11111111111111111111111111111111111111112"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
JITO = {"96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5", "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe", "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY", "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49", "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh", "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt", "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL", "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT"}


def b58dec(s):
    n = 0
    for c in s:
        n = n * 58 + B58.index(c)
    return n.to_bytes((n.bit_length() + 7) // 8, "big")


def rpc(m, p):
    req = urllib.request.Request(RPC, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"})
    for i in range(6):
        try:
            return json.load(urllib.request.urlopen(req, timeout=25)).get("result")
        except Exception:
            time.sleep(0.4 * (i + 1))
    return None


def relaylab(dests):
    for d in dests:
        if d.startswith("moon"):
            return "LunarLander"
        if d.startswith("noz") or d == "TEMPaMeCRFAS9EKF53Jd6KpHxgL47uWLcpFArU1Fanq":
            return "Nozomi"
        if d in JITO:
            return "Jito"
        if d.startswith("4ACf") or d.startswith("5VY9") or d.startswith("9bnz") or d.startswith("D2L6"):
            return "Helius"
        if d.startswith("astra") or d.startswith("AStR"):
            return "Astralane"
        if d.startswith("rapid"):
            return "rapid"
    return "direct/no-tip" if not dests else "other:" + dests[0][:6]


# oldest ~20 sigs
sgs = []
before = None
while True:
    prm = [MINT, {"limit": 1000}] if before is None else [MINT, {"limit": 1000, "before": before}]
    r = rpc("getSignaturesForAddress", prm)
    if not r:
        break
    sgs += r
    if len(r) < 1000:
        break
    before = r[-1]["signature"]
    if len(sgs) > 9000:
        break
early = sgs[-20:][::-1]  # oldest first
dev_lam = None


def analyze(s):
    tx = rpc("getTransaction", [s["signature"], {"maxSupportedTransactionVersion": 0, "encoding": "jsonParsed"}])
    if not tx or not tx.get("meta") or tx["meta"].get("err"):
        return None
    logs = tx["meta"].get("logMessages", [])
    is_buy = any("Instruction: Buy" in l for l in logs)
    is_create = any("Instruction: Create" in l for l in logs)
    if not (is_buy or is_create):
        return None
    msg = tx["transaction"]["message"]
    keys = [k["pubkey"] for k in msg["accountKeys"]]
    payer = keys[0]
    # tokens received by payer (mint) and sol spent
    pre = {b["mint"]: float(b["uiTokenAmount"]["uiAmount"] or 0) for b in tx["meta"].get("preTokenBalances", []) if b.get("owner") == payer}
    post = {b["mint"]: float(b["uiTokenAmount"]["uiAmount"] or 0) for b in tx["meta"].get("postTokenBalances", []) if b.get("owner") == payer}
    tok = post.get(MINT, 0) - pre.get(MINT, 0)
    si = keys.index(payer)
    sol = (tx["meta"]["preBalances"][si] - tx["meta"]["postBalances"][si]) / 1e9
    cu_price = cu_lim = None
    dests = []
    tip = 0
    allix = list(msg.get("instructions", []))
    for inner in tx["meta"].get("innerInstructions", []):
        allix += inner["instructions"]
    for ix in allix:
        if ix.get("programId") == CB and "data" in ix:
            raw = b58dec(ix["data"])
            if raw and raw[0] == 0x02 and len(raw) >= 5:
                cu_lim = int.from_bytes(raw[1:5], "little")
            elif raw and raw[0] == 0x03 and len(raw) >= 9:
                cu_price = int.from_bytes(raw[1:9], "little")
        pj = ix.get("parsed")
        if ix.get("program") == "system" and isinstance(pj, dict) and pj.get("type") == "transfer":
            lam = int(pj["info"].get("lamports", 0))
            dst = pj["info"].get("destination", "")
            if 50000 <= lam <= 60000000 and dst != payer:
                dests.append(dst)
                tip = max(tip, lam)
    eff = (sol / tok) if tok > 0 else 0  # SOL per token = effective price
    return {"payer": payer, "sol": sol, "tok": tok, "eff": eff, "cu_price": cu_price, "cu_lim": cu_lim, "tip": tip, "relay": relaylab(dests), "create": is_create}


res = []
with cf.ThreadPoolExecutor(max_workers=10) as ex:
    for r in ex.map(analyze, early):
        if r:
            res.append(r)
# floor px from dev buy (the create tx's sol)
dev = next((r["sol"] for r in res if r["create"]), 0)
floor = (30e9 + dev * 1e9) ** 2 / (30e9 * 1.073e15)
for r in res:
    r["fill"] = (r["eff"] / floor) if r["eff"] and floor else 0
# rank by fill (lowest = front)
res = [r for r in res if r["tok"] > 0]
res.sort(key=lambda r: r["fill"])
print(f"dev buy ~{dev:.2f} SOL. Front-landers ranked by fill (low=front):")
print(f"{'fill':>6} {'who':10} {'sol_in':>7} {'cu_price':>9} {'cu_lim':>7} {'tip_SOL':>8} {'relay'}")
for r in res[:12]:
    print(f"{r['fill']:>6.3f} {r['payer'][:10]} {r['sol']:>7.3f} {str(r['cu_price']):>9} {str(r['cu_lim']):>7} {r['tip']/1e9:>8.4f} {r['relay']}")
