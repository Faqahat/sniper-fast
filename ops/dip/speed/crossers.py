#!/usr/bin/env python3
# READ-ONLY: the wallets that pushed the price over our guard before we landed (miss_analysis.json): for each, the crossing tx
# (send path from tip recipients, priority, CU limit / used, own router program?, Lighthouse guard?) and the wallet's last 1000
# txs (fail rate, and how many of its successful buys are pump buys via its own program vs direct).
import json, collections, importlib.util, statistics
spec = importlib.util.spec_from_file_location("osp", "/home/moiz/sniper/ops/speedcheck/our_speed.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
KNOWN = {"6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "pump", "ComputeBudget111111111111111111111111111111": "cb", "11111111111111111111111111111111": "system",
         "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL": "ata", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb": "token22", "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA": "token",
         "L2TExMFKdjpN9kozasaurPirfHy9P8sbXoAN1qA3S95": "lighthouse", "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr": "memo"}
rows = [r for r in json.load(open("/home/moiz/sniper/ops/dip/speed/miss_analysis.json")) if r.get("cross_sig")]
wallets = {}
for r in rows:
    t = S.rpc("getTransaction", [r["cross_sig"], {"encoding": "json", "maxSupportedTransactionVersion": 0}])
    if not t: continue
    msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}; keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    signer = keys[0]; cu_price = cu_limit = 0; tips = []; progs = []
    for ix in msg["instructions"]:
        pr = keys[ix["programIdIndex"]]; d = S.b58dec(ix["data"]); progs.append(KNOWN.get(pr, pr[:8]))
        if pr == S.CB and d:
            if d[0] == 3: cu_price = int.from_bytes(d[1:9], "little")
            elif d[0] == 2: cu_limit = int.from_bytes(d[1:5], "little")
        if pr == S.SYS and len(d) >= 12 and int.from_bytes(d[:4], "little") == 2:
            to = keys[ix["accounts"][1]]
            if to in S.TIP: tips.append((S.TIP[to], int.from_bytes(d[4:12], "little")))
    w = wallets.setdefault(signer, dict(n=0, ms=[], tips=collections.Counter(), tip_sol=[], prio=[], cu=[], used=[], progs=collections.Counter(), clients=collections.Counter()))
    w["n"] += 1; w["ms"].append(r["cross_ms"]); w["prio"].append(cu_price * (cu_limit or 200000) / 1e15); w["cu"].append(cu_limit); w["used"].append(t["meta"].get("computeUnitsConsumed"))
    w["tip_sol"].append(sum(x for _, x in tips) / 1e9); w["clients"][r["client"]] += 1
    for s, _ in tips: w["tips"][s] += 1
    if not tips: w["tips"]["no tip"] += 1
    for p in set(progs) - {"cb", "system", "ata", "token", "token22"}: w["progs"][p] += 1
print(f"{'wallet':10s} n  crossed at (ms)  path(s) of the crossing txs        tip SOL  priority SOL  CU limit/used   programs")
for wl, w in sorted(wallets.items(), key=lambda kv: -kv[1]["n"]):
    print(f"{wl[:8]:10s} {w['n']}  {sorted(round(x) for x in w['ms'])}  {dict(w['tips'])}  {statistics.median(w['tip_sol']):.4f}  {statistics.median(w['prio']):.5f}  "
          f"{statistics.median(w['cu']):,.0f}/{statistics.median([u for u in w['used'] if u]):,.0f}  {dict(w['progs'])}  leaders {dict(w['clients'])}")
print("\nwallet fail rates (last 1000 txs):")
for wl, w in sorted(wallets.items(), key=lambda kv: -kv[1]["n"])[:10]:
    sigs = S.rpc("getSignaturesForAddress", [wl, {"limit": 1000}]) or []
    f = sum(1 for s in sigs if s.get("err"))
    span = (sigs[0].get("blockTime", 0) - sigs[-1].get("blockTime", 0)) / 3600 if len(sigs) > 1 else 0
    print(f"  {wl[:8]}: {f} of {len(sigs)} failed ({100 * f / max(1, len(sigs)):.1f}%) over {span:.1f} h")
