#!/usr/bin/env python3
# Every FRZ pump BUY attempt (successful tiny buys AND fail-by-design probes, which still land in blocks): landing delay
# after the token's create on the replay's block-position scale, fee, tips / routes, leader client. READ-ONLY RPC.
import sys, json, time, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/speedcheck")
import importlib.util
spec = importlib.util.spec_from_file_location("osp", "/home/moiz/sniper/ops/speedcheck/our_speed.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
W = sys.argv[1]; LABEL = sys.argv[2]
BUY_MINT_POS = {"66063d1201daebea": 2, "38fc74089edfcd5f": 2, "e1f7501ed5b38488": 1, "07051dc4f5176550": 1, "c2ab1c46684d5b2f": 1, "b817ee6167c5d33d": 1}
page = S.rpc("getSignaturesForAddress", [W, {"limit": 1000}]) or []
rows = []
for p in page:
    t = S.rpc("getTransaction", [p["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    if not t: continue
    msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    mint = None
    for ix in msg["instructions"]:
        if keys[ix["programIdIndex"]] != S.PUMP: continue
        d = S.b58dec(ix["data"]); mp = BUY_MINT_POS.get(d[:8].hex())
        if mp is not None and len(ix["accounts"]) > mp: mint = keys[ix["accounts"][mp]]; break
    if not mint: continue
    cu_price = cu_limit = None; tips = []
    for ix in msg["instructions"]:
        pr = keys[ix["programIdIndex"]]; d = S.b58dec(ix["data"])
        if pr == S.CB and d:
            if d[0] == 3: cu_price = int.from_bytes(d[1:9], "little")
            elif d[0] == 2: cu_limit = int.from_bytes(d[1:5], "little")
        elif pr == S.SYS and len(d) >= 12 and int.from_bytes(d[:4], "little") == 2:
            to = keys[ix["accounts"][1]]
            if to in S.TIP: tips.append((S.TIP[to], int.from_bytes(d[4:12], "little")))
    c = S.create_of(mint, p["signature"])
    if not c: continue
    pb = S.pos(t["slot"], p["signature"]); pc = S.pos(c["slot"], c["sig"])
    if not pb or not pc: continue
    ms = (t["slot"] - c["slot"]) * S.SLOT_MS + (pb[0] / pb[1] - pc[0] / pc[1]) * S.SLOT_MS
    rows.append(dict(sig=p["signature"], when=time.strftime("%m-%d %H:%M:%S", time.gmtime((t.get("blockTime") or 0) + 18000)), ok=t["meta"]["err"] is None,
                     mint=mint, dslot=t["slot"] - c["slot"], ms=round(ms, 1), idx=pb[0], size=pb[1], fee=t["meta"]["fee"], tips=tips,
                     prio=(cu_price or 0) * (cu_limit or 0) / 1e15, client=S.leader_client(t["slot"])))
rows.sort(key=lambda r: r["when"])
json.dump(rows, open(f"/home/moiz/sniper/ops/speedcheck/{LABEL}_all_buys.json", "w"), indent=1)
for r in rows:
    tips = ", ".join(f"{s} {x / 1e9:.4f}" for s, x in r["tips"]) or "none"
    print(f"{r['when']} {'buy  ' if r['ok'] else 'PROBE'} {r['mint'][:6]} | +{r['dslot']} slot {r['ms']:6.1f} ms | idx {r['idx']}/{r['size']} | fee {r['fee'] / 1e9:.5f} | tips [{tips}] | leader {r['client']}")
ms = [r["ms"] for r in rows]
if ms: print(f"{LABEL}: {len(rows)} buy attempts, median {statistics.median(ms):.1f} ms, same slot as the create {sum(1 for r in rows if r['dslot'] == 0)}/{len(rows)}")
