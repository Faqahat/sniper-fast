#!/usr/bin/env python3
# READ-ONLY: how does a dip bot avoid failed txs? Its last N signatures (failed share), then a sample of its txs: programs
# invoked (own router?), tip recipients -> send service, CU price / limit, pump buy instruction + its slippage args,
# whether a successful tx actually traded (pump TradeEvent) or was a no-op, and Jito-bundle markers.
# usage: python3 -I haqq_path.py <wallet> [sample]
import sys, json, collections, base64, importlib.util
spec = importlib.util.spec_from_file_location("osp", "/home/moiz/sniper/ops/speedcheck/our_speed.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
W = sys.argv[1]; NS = int(sys.argv[2]) if len(sys.argv) > 2 else 40
sigs = S.rpc("getSignaturesForAddress", [W, {"limit": 1000}]) or []
fail = [s for s in sigs if s.get("err")]
print(f"{W[:8]}: last {len(sigs)} txs, failed {len(fail)} ({100 * len(fail) / max(1, len(sigs)):.1f}%)")
KNOWN = {"6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "pump", "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA": "pumpswap", "ComputeBudget111111111111111111111111111111": "cb",
         "11111111111111111111111111111111": "system", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL": "ata", "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA": "token",
         "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb": "token22", "L2TExMFKdjpN9kozasaurPirfHy9P8sbXoAN1qA3S95": "lighthouse", "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ": "pump-fees"}
progs = collections.Counter(); tips = collections.Counter(); traded = 0; noop = 0; cu_prices = []; buy_discs = collections.Counter(); inner = collections.Counter()
for s in [x for x in sigs if not x.get("err")][:NS]:
    t = S.rpc("getTransaction", [s["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 0}])
    if not t: continue
    msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    for ix in msg["instructions"]:
        pr = keys[ix["programIdIndex"]]; progs[KNOWN.get(pr, pr[:8])] += 1; d = S.b58dec(ix["data"])
        if pr == S.CB and d and d[0] == 3: cu_prices.append(int.from_bytes(d[1:9], "little"))
        if pr == S.SYS and len(d) >= 12 and int.from_bytes(d[:4], "little") == 2:
            to = keys[ix["accounts"][1]]
            if to in S.TIP: tips[S.TIP[to]] += 1
        if KNOWN.get(pr) == "pump": buy_discs[d[:8].hex()] += 1
    for ii in t["meta"].get("innerInstructions") or []:
        for ix in ii["instructions"]:
            pr = keys[ix["programIdIndex"]]
            if KNOWN.get(pr) == "pump": inner[S.b58dec(ix["data"])[:8].hex()] += 1
    logs = " ".join(t["meta"].get("logMessages") or [])
    if "Instruction: Buy" in logs or "Instruction: Sell" in logs or "TradeEvent" in logs or "vdt/007mYe" in logs: traded += 1
    else: noop += 1
print(f"sample of {traded + noop} successful txs: traded {traded}, no trade (no-op) {noop}")
print("top-level programs:", dict(progs.most_common(12)))
print("pump instructions top-level:", dict(buy_discs), "| via CPI (inner):", dict(inner))
print("tips by service:", dict(tips))
if cu_prices: print(f"CU price median {sorted(cu_prices)[len(cu_prices) // 2]:,} uL/CU (min {min(cu_prices):,}, max {max(cu_prices):,})")
if fail: print("failed examples:", [f['signature'][:12] + ' ' + json.dumps(f['err'])[:60] for f in fail[:3]])
