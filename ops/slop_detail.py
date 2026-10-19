import json, urllib.request, os, time
TOK = os.environ["CONSTANTK_TOKEN"]
RPC = f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
MINT = "2yxjYSyAY3sYgBWy9HbgFgfASvWByfDKpSjK94Wbpump"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
FOUR = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"


def rpc(m, p):
    req = urllib.request.Request(RPC, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"})
    for i in range(6):
        try:
            return json.load(urllib.request.urlopen(req, timeout=25)).get("result")
        except Exception:
            time.sleep(0.3 * (i + 1))
    return None


# all sigs oldest-first
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
sgs = sgs[::-1]  # oldest first
create_slot = sgs[0].get("slot")
print("total txs:", len(sgs), "create_slot:", create_slot)

# 1) CREATE tx: is there a bundled buy in it? (what the engine reads as dev_buy)
tx0 = rpc("getTransaction", [sgs[0]["signature"], {"maxSupportedTransactionVersion": 0, "encoding": "jsonParsed"}])
keys0 = [k["pubkey"] for k in tx0["transaction"]["message"]["accountKeys"]]
logs0 = tx0["meta"].get("logMessages", [])
has_buy_in_create = any("Instruction: Buy" in l for l in logs0)
signer0 = next((k["pubkey"] for k in tx0["transaction"]["message"]["accountKeys"] if k.get("signer")), None)
sol0 = (tx0["meta"]["preBalances"][keys0.index(signer0)] - tx0["meta"]["postBalances"][keys0.index(signer0)]) / 1e9 if signer0 else 0
print(f"\nCREATE tx: fee_payer={signer0[:10]}  buy_bundled_in_create={has_buy_in_create}  payer_SOL_spent={sol0:.3f}")

# 2) scan first ~40 txs: who bought, how much, slot delta. Flag the DEV (creator) and 4yFAz.
print("\nfirst buys (slot delta, buyer, SOL spent):")
fouraz_buy = None
dev_buy = None
for i, s in enumerate(sgs[:40]):
    t = rpc("getTransaction", [s["signature"], {"maxSupportedTransactionVersion": 0, "encoding": "jsonParsed"}])
    if not t or not t.get("meta"):
        continue
    logs = t["meta"].get("logMessages", [])
    if not any("Instruction: Buy" in l for l in logs) and i > 0:
        continue
    keys = [k["pubkey"] for k in t["transaction"]["message"]["accountKeys"]]
    signer = next((k["pubkey"] for k in t["transaction"]["message"]["accountKeys"] if k.get("signer")), None)
    sd = (s.get("slot", 0) - create_slot)
    spent = (t["meta"]["preBalances"][keys.index(signer)] - t["meta"]["postBalances"][keys.index(signer)]) / 1e9 if signer in keys else 0
    is4 = (signer == FOUR) or (FOUR in keys)
    tag = " <<< 4yFAz" if is4 else (" (creator/dev)" if i == 0 or signer == signer0 else "")
    if i < 12 or is4:
        print(f"  d{sd:+d} {signer[:10]} spent={spent:+.3f} SOL{tag}")
    if is4 and fouraz_buy is None and spent > 0.001:
        fouraz_buy = (sd, spent, s["signature"])
    if i == 0 and spent > 0.001:
        dev_buy = spent

print(f"\n=== SUMMARY ===")
print(f"create fee-payer (dev) spent in create tx: {sol0:.3f} SOL (buy bundled: {has_buy_in_create})")
if fouraz_buy:
    print(f"4yFAz BOUGHT: slot delta d{fouraz_buy[0]:+d}, spent {fouraz_buy[1]:.3f} SOL")
else:
    print("4yFAz buy: NOT FOUND in first 40 txs (may have bought later)")
