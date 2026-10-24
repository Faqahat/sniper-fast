#!/usr/bin/env python3
# READ-ONLY: how many send paths do competitors use per trade? Per wallet, its last N txs: tip transfers per tx (distinct services
# = paths the SAME signed tx was sent to), durable nonce (first ix System AdvanceNonceAccount = one copy per path, only one can
# land), and bursts = several txs of the wallet on the same token within 2 slots (spray: more copies / retries per trade).
import sys, json, collections, statistics, importlib.util
spec = importlib.util.spec_from_file_location("osp", "/home/moiz/sniper/ops/speedcheck/our_speed.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
W = {"HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ": "HkQ7hMjy", "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq": "haqqiUUX", "DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw": "DYXDDrZC"}
N = int(sys.argv[1]) if len(sys.argv) > 1 else 60
extra = sys.argv[2:]                                   # more wallets (full addresses)
for a in extra: W[a] = a[:8]
for w, name in W.items():
    sigs = (S.rpc("getSignaturesForAddress", [w, {"limit": N}]) or [])[:N]
    per_tx = []; nonce = 0; by_mint = collections.defaultdict(list); n_ok = n_fail = 0; svc_ct = collections.Counter()
    for s in sigs:
        t = S.rpc("getTransaction", [s["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 0}])
        if not t: continue
        msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}; keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
        ixs = msg["instructions"]; tips = []
        if ixs:
            d0 = S.b58dec(ixs[0]["data"])
            if keys[ixs[0]["programIdIndex"]] == S.SYS and len(d0) >= 4 and int.from_bytes(d0[:4], "little") == 4: nonce += 1
        for ix in ixs:
            if keys[ix["programIdIndex"]] == S.SYS:
                d = S.b58dec(ix["data"])
                if len(d) >= 12 and int.from_bytes(d[:4], "little") == 2:
                    to = keys[ix["accounts"][1]]
                    if to in S.TIP: tips.append(S.TIP[to])
        per_tx.append(len(set(tips))); svc_ct.update(set(tips))
        ok = t["meta"]["err"] is None; n_ok += ok; n_fail += (not ok)
        mints = {b["mint"] for b in (t["meta"].get("postTokenBalances") or []) + (t["meta"].get("preTokenBalances") or []) if b.get("owner") == w
                 and b["mint"] != "So11111111111111111111111111111111111111112"}
        for m in mints: by_mint[m].append((t["slot"], ok))
    bursts = []
    for m, v in by_mint.items():
        v.sort()
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[j + 1][0] - v[i][0] <= 2: j += 1
            if j > i: bursts.append(v[i:j + 1])
            i = j + 1
    dist = collections.Counter(per_tx)
    print(f"{name}: {len(per_tx)} txs ({n_ok} ok / {n_fail} failed) | tip services per tx: " + ", ".join(f"{k} paths x{dist[k]}" for k in sorted(dist))
          + f" | durable nonce in {nonce} txs | services seen {dict(svc_ct.most_common(8))}")
    if bursts:
        print(f"   bursts (same token, ≤ 2 slots): {len(bursts)}; sizes {sorted(len(b) for b in bursts)}; e.g. " + "; ".join(
            "[" + " ".join(("ok" if ok else "FAIL") + f"@{sl - b[0][0]}" for sl, ok in b) + "]" for b in bursts[:4]))
