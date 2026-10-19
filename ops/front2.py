import json, urllib.request, os, time
TOK = os.environ["CONSTANTK_TOKEN"]
RPC = f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
MINT = "JE9LHzWe2ovReNuxPBfxvfAci18gr54nRpcsGLG6pump"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
CB = "ComputeBudget111111111111111111111111111111"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
JITO = {"96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5", "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe", "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY", "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49", "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh", "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt", "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL", "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT"}


def b58dec(s):
    n = 0
    for c in s:
        n = n * 58 + B58.index(c)
    return n.to_bytes((n.bit_length() + 7) // 8, "big")


def rpc(m, p, to=40):
    req = urllib.request.Request(RPC, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"})
    for i in range(6):
        try:
            return json.load(urllib.request.urlopen(req, timeout=to)).get("result")
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


sgs = rpc("getSignaturesForAddress", [MINT, {"limit": 1000}])
cs = sgs[-1]["slot"] if sgs else None
# page to oldest for create_slot
before = sgs[-1]["signature"] if sgs and len(sgs) == 1000 else None
while before:
    r = rpc("getSignaturesForAddress", [MINT, {"limit": 1000, "before": before}])
    if not r:
        break
    cs = r[-1]["slot"]
    before = r[-1]["signature"] if len(r) == 1000 else None
print("create_slot:", cs)
blk = rpc("getBlock", [cs, {"maxSupportedTransactionVersion": 0, "transactionDetails": "accounts", "rewards": False}], to=60)
if not blk:
    print("no block (accounts mode)")
    raise SystemExit
# ordered txs touching the mint
front = []
for pos, tx in enumerate(blk["transactions"]):
    acct = tx.get("transaction", {}).get("accountKeys", [])
    pks = [a["pubkey"] for a in acct]
    if MINT in pks and PUMP in pks:
        if tx.get("meta", {}).get("err"):
            continue
        sig = tx["transaction"]["signatures"][0]
        payer = pks[0]
        front.append((pos, sig, payer))
    if len(front) >= 8:
        break
print(f"first {len(front)} mint txs in the creation block:")
print(f"{'rank':4} {'who':10} {'cu_price':>9} {'cu_lim':>7} {'tip_SOL':>8} {'relay'}")
for i, (pos, sig, payer) in enumerate(front):
    tx = rpc("getTransaction", [sig, {"maxSupportedTransactionVersion": 0, "encoding": "jsonParsed"}])
    cu_price = cu_lim = None
    dests = []
    tip = 0
    if tx:
        msg = tx["transaction"]["message"]
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
                if 50000 <= lam <= 50000000 and dst != payer:
                    dests.append(dst)
                    tip = max(tip, lam)
    logs = tx["meta"].get("logMessages", []) if tx else []
    tag = "(DEV/create)" if any("Instruction: Create" in l for l in logs) else ""
    print(f"{i:4} {payer[:10]} {str(cu_price):>9} {str(cu_lim):>7} {tip/1e9:>8.4f} {relaylab(dests)} {tag}")
