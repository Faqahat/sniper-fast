import json, urllib.request, os, time, base64
TOK = os.environ["CONSTANTK_TOKEN"]
RPC = f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
MINT = "JE9LHzWe2ovReNuxPBfxvfAci18gr54nRpcsGLG6pump"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
CB = "ComputeBudget111111111111111111111111111111"
SYS = "11111111111111111111111111111111"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
# relay tip account prefixes / sets
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
            return json.load(urllib.request.urlopen(req, timeout=40)).get("result")
        except Exception:
            time.sleep(0.4 * (i + 1))
    return None


def relay(dests, lam):
    for d in dests:
        if d.startswith("moon"):
            return "LunarLander"
        if d.startswith("noz") or d == "TEMPaMeCRFAS9EKF53Jd6KpHxgL47uWLcpFArU1Fanq":
            return "Nozomi"
        if d in JITO:
            return "Jito"
        if d.startswith("4ACf") or d.startswith("5VY9") or d.startswith("9bnz"):
            return "Helius"
        if d.startswith("astra") or d.startswith("AStR"):
            return "Astralane"
        if d.startswith("rapid"):
            return "rapid"
        if d.startswith("0slot") or d.lower().startswith("zero"):
            return "0slot"
    return "direct/no-tip" if not dests else ("other-tip " + dests[0][:6])


# create slot
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
create_slot = sgs[-1]["slot"]
print(f"token sigs: {len(sgs)}  create_slot: {create_slot}")

blk = rpc("getBlock", [create_slot, {"maxSupportedTransactionVersion": 0, "transactionDetails": "full", "rewards": False, "encoding": "jsonParsed"}])
if not blk:
    print("no block")
    raise SystemExit
K = 30e9 * 1.073e15


def floor_px(dev):
    return (30e9 + dev) ** 2 / (30e9 * 1.073e15)


buyers = []
for pos, tx in enumerate(blk["transactions"]):
    meta = tx.get("meta")
    if not meta or meta.get("err"):
        continue
    msg = tx["transaction"]["message"]
    keys = [k["pubkey"] for k in msg["accountKeys"]]
    if MINT not in keys or PUMP not in keys:
        continue
    logs = meta.get("logMessages", [])
    if not any("Instruction: Buy" in l or "Instruction: Create" in l for l in logs):
        continue
    is_create = any("Instruction: Create" in l for l in logs)
    signer = next((k["pubkey"] for k in msg["accountKeys"] if k.get("signer")), "?")
    # sol spent by signer
    si = keys.index(signer)
    sol_in = (meta["preBalances"][si] - meta["postBalances"][si]) / 1e9
    # cu_price/cu_limit + tips
    cu_price = cu_limit = None
    dests = []
    allix = list(msg.get("instructions", []))
    for inner in meta.get("innerInstructions", []):
        allix += inner["instructions"]
    for ix in allix:
        if ix.get("programId") == CB and "data" in ix:
            raw = b58dec(ix["data"])
            if raw and raw[0] == 0x02 and len(raw) >= 5:
                cu_limit = int.from_bytes(raw[1:5], "little")
            elif raw and raw[0] == 0x03 and len(raw) >= 9:
                cu_price = int.from_bytes(raw[1:9], "little")
        pj = ix.get("parsed")
        if ix.get("program") == "system" and isinstance(pj, dict) and pj.get("type") == "transfer":
            lam = int(pj["info"].get("lamports", 0))
            dst = pj["info"].get("destination", "")
            if 50000 <= lam <= 50000000 and dst != signer:
                dests.append(dst)
    buyers.append({"pos": pos, "signer": signer, "sol_in": sol_in, "cu_price": cu_price, "cu_limit": cu_limit, "dests": dests, "is_create": is_create})

buyers.sort(key=lambda b: b["pos"])
print(f"\ncreation-slot buyers (in block order): {len(buyers)}")
print(f"{'rank':4} {'who':10} {'sol_in':>7} {'cu_price':>9} {'cu_lim':>7} {'tip':>7} {'relay'}")
dev = buyers[0]["sol_in"] if buyers else 0
for i, b in enumerate(buyers[:12]):
    tip = 0
    # recompute tip lamports from dests (approx: look again)
    rel = relay(b["dests"], 0)
    tag = "(DEV/create)" if b["is_create"] else ""
    print(f"{i:4} {b['signer'][:10]} {b['sol_in']:>7.3f} {str(b['cu_price']):>9} {str(b['cu_limit']):>7} {len(b['dests']):>4}tx {rel} {tag}")
