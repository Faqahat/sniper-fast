#!/usr/bin/env python3
# READ-ONLY: print the txs around each pump.fun create in given slots (payer, signers, tip provider).
import json, sys, urllib.request

RPC = sys.argv[1]
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
tips = {}
for prov, v in json.load(open("/root/arbx-fast/data/sender-tip-accounts.json")).items():
    if isinstance(v, dict) and isinstance(v.get("tip_accounts"), list):
        for a in v["tip_accounts"]:
            tips.setdefault(a, prov)


def rpc(m, p):
    r = urllib.request.Request(RPC, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(),
                               headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=30))


for slot in map(int, sys.argv[2:]):
    txs = rpc("getBlock", [slot, {"encoding": "json", "maxSupportedTransactionVersion": 1, "transactionDetails": "full",
                                  "rewards": False}])["result"]["transactions"]
    for i, t in enumerate(txs):
        logs = (t.get("meta") or {}).get("logMessages") or []
        keys = t["transaction"]["message"]["accountKeys"]
        if PUMP in keys and any(l.startswith("Program log: Instruction: Create") for l in logs):
            print(f"slot {slot} create at idx {i}")
            for j in range(max(0, i - 2), min(len(txs), i + 5)):
                tt = txs[j]; k = tt["transaction"]["message"]["accountKeys"]
                nsig = tt["transaction"]["message"]["header"]["numRequiredSignatures"]
                prov = [tips[x] for x in k if x in tips]
                pumpix = any(x == PUMP for x in k)
                print(f"   {j-i:+d} payer={k[0][:8]} signers={[x[:6] for x in k[:nsig]]} tip={prov} pump={pumpix} err={tt['meta']['err'] is not None}")
