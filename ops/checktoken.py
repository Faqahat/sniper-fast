import json, urllib.request, os, time
TOK = os.environ["CONSTANTK_TOKEN"]
RPC = f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
MINT = "2yxjYSyAY3sYgBWy9HbgFgfASvWByfDKpSjK94Wbpump"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
WSOL = "So11111111111111111111111111111111111111112"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
WL = {"ipfs.io", "metadata.j7tracker.io", "m.rapidlaunch.io", "gateway.pinata.cloud"}
BOT = {"gg.sc", "ipfs.launchblitz.ai", "pf.jake-98f.workers.dev", "storage.googleapis.com"}


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
            time.sleep(0.3 * (i + 1))
    return None


def parse_create(raw):
    # disc(8) name sym uri creator(32) [v2 flags]
    p = 8
    out = {}
    names = []
    for i in range(3):
        ln = int.from_bytes(raw[p:p + 4], "little")
        start = p + 4
        end = start + ln
        names.append(raw[start:end].decode("utf-8", "replace"))
        p = end
    out["name"], out["symbol"], out["uri"] = names
    p += 32  # creator
    # v2 flags: is_mayhem(1) is_cashback(1) creator_fee_bps(8) is_holder_reward(1)
    out["is_mayhem"] = raw[p] != 0 if p < len(raw) else False
    out["creator_fee_bps"] = int.from_bytes(raw[p + 2:p + 10], "little") if p + 10 <= len(raw) else 0
    return out


# oldest tx = create
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
    if len(sgs) > 8000:
        break
print("total txs on mint:", len(sgs))
create = sgs[-1]
tx = rpc("getTransaction", [create["signature"], {"maxSupportedTransactionVersion": 0, "encoding": "jsonParsed"}])
ixs = list(tx["transaction"]["message"].get("instructions", []))
for inner in tx["meta"].get("innerInstructions", []):
    ixs += inner["instructions"]
cr = None
for ix in ixs:
    if ix.get("programId") == PUMP and "data" in ix:
        raw = b58dec(ix["data"])
        if len(raw) > 60:
            cr = parse_create(raw)
            break
host = cr["uri"].split("://", 1)[-1].split("/", 1)[0] if cr and cr["uri"] else "(none)"
# dev buy: scan the create-slot txs for the biggest SOL-out buy on this mint (the dev's same-slot buy)
create_slot = create.get("slot")
dev_sol = 0.0
for s in sgs[-6:]:  # earliest few txs
    t = rpc("getTransaction", [s["signature"], {"maxSupportedTransactionVersion": 0, "encoding": "jsonParsed"}])
    if not t or not t.get("meta"):
        continue
    logs = t["meta"].get("logMessages", [])
    if not any("Instruction: Buy" in l for l in logs):
        continue
    # SOL spent by fee payer (dev) in this buy
    keys = [k["pubkey"] for k in t["transaction"]["message"]["accountKeys"]]
    signer = next((k["pubkey"] for k in t["transaction"]["message"]["accountKeys"] if k.get("signer")), None)
    if signer and signer in keys:
        i = keys.index(signer)
        d = (t["meta"]["preBalances"][i] - t["meta"]["postBalances"][i]) / 1e9
        dev_sol = max(dev_sol, d)

name = cr["name"] if cr else "?"
sym = cr["symbol"] if cr else "?"
print(f"\nNAME: {name!r}  SYMBOL: {sym!r}")
print(f"URI host: {host}")
print(f"dev buy (est, largest same-slot buy): {dev_sol:.3f} SOL")
print(f"vanilla: mayhem={cr['is_mayhem'] if cr else '?'} creator_fee_bps={cr['creator_fee_bps'] if cr else '?'}")
print("\n=== FILTER CHECK ===")
# host
if host in WL:
    hv = "PASS (trusted whitelist)"
elif host in BOT or host.endswith(".trycloudflare.com"):
    hv = "FAIL (bot-launchpad)"
else:
    hv = f"not in 4-host whitelist, not a bot ({host}) -> whitelist=FAIL, blacklist=PASS"
print("URI-host:", hv)
# dev band
print("dev 2-3 SOL:", "PASS" if 2.0 <= dev_sol <= 3.0 else f"FAIL (dev={dev_sol:.2f})")
print("dev 0.8-3 SOL:", "PASS" if 0.8 <= dev_sol <= 3.0 else f"FAIL (dev={dev_sol:.2f})")
# new loser-separator (agent)
low = name == name.lower() and name.strip() != ""
roundd = abs(dev_sol - round(dev_sol)) < 0.03 and dev_sol >= 1.0
print("name all-lowercase (reject signal):", "YES-REJECT" if low else "no")
print("round-dev N.0 SOL (reject signal):", f"YES-REJECT (~{round(dev_sol)}.0)" if roundd else "no")
