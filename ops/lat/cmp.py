import sys, json, base64
sys.path.insert(0, "/root/indep")
from common import rpc, get_block, events, is_vote, b58dec
MINT = "4sesi1KB1JGsfe1AcNYoTXpgW4JcTEkRKGKsRfJZpump"
SLOT = 458914631
WHO = {"9XPMCaxt": "FAST SNIPER (+8)", "FRZh63L6": "US"}
CB = "ComputeBudget111111111111111111111111111111"
b = get_block(SLOT)
nv = [t for t in b["transactions"] if not is_vote(t)]
ci = next(i for i, t in enumerate(nv) if any(c["mint"] == MINT for c in events((t.get("meta") or {}).get("logMessages"))[1]))
for i, t in enumerate(nv):
    msg = t["transaction"]["message"]
    payer = msg["accountKeys"][0]
    tag = WHO.get(payer[:8])
    if not tag:
        continue
    meta = t["meta"]
    la = meta.get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    cu_lim = cu_price = None
    progs, tips = [], []
    for ix in msg["instructions"]:
        p = keys[ix["programIdIndex"]]
        progs.append(p[:8])
        if p == CB:
            d = b58dec(ix["data"])
            if d[0] == 2: cu_lim = int.from_bytes(d[1:5], "little")
            if d[0] == 3: cu_price = int.from_bytes(d[1:9], "little")
    pre, post = meta["preBalances"], meta["postBalances"]
    for k in range(msg["header"]["numRequiredSignatures"], len(post)):
        dlt = post[k] - pre[k]
        if 0 < dlt <= 100_000_000 and keys[k] not in (MINT,):
            tips.append((keys[k][:8], dlt / 1e9))
    raw = base64.b64decode(rpc("getTransaction", [t["transaction"]["signatures"][0], {"encoding": "base64", "maxSupportedTransactionVersion": 1}])["transaction"][0])
    ev = [e for e in events(meta.get("logMessages"))[0] if e["mint"] == MINT]
    print(f"\n== {tag}  sig {t['transaction']['signatures'][0][:16]}")
    print(f"  position after create: +{i - ci}  (create at {ci}, block has {len(nv)} non-vote txs)")
    print(f"  buy SOL {sum(e['sol'] for e in ev if e['buy'])/1e9:.4f}")
    print(f"  CU limit {cu_lim}  CU used {meta.get('computeUnitsConsumed')}  CU price {cu_price} µlam  -> priority {((cu_price or 0)*(cu_lim or 0))/1e15:.5f} SOL; total fee {meta['fee']/1e9:.5f}")
    print(f"  tx size {len(raw)} bytes, version {t.get('version')}, lookup tables {len(msg.get('addressTableLookups') or [])}, accounts {len(keys)}, signers {msg['header']['numRequiredSignatures']}")
    print(f"  top-level programs {progs}")
    print(f"  SOL credited to small accounts (tips/fees): {tips}")
