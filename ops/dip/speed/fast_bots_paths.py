#!/usr/bin/env python3
# READ-ONLY: the buys that got in AHEAD of our dip buys (FRZ live tests 10-24, tape events between the dump and our buy) and
# the buys that came right after: their send path (tip recipients -> service), priority fee (CU price x limit), CU limit,
# Jito-style bundle or not, block-position ms after the dump, and the leader client -> what fast bots pay / use per leader.
# usage: python3 -I fast_bots_paths.py run1.jsonl [run2.jsonl ...]
import sys, json, statistics, collections, importlib.util
spec = importlib.util.spec_from_file_location("osp", "/home/moiz/sniper/ops/speedcheck/our_speed.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
W = "FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS"
rows = []
for run in sys.argv[1:]:
    ev = [json.loads(l) for l in open(run)]
    for f in [e for e in ev if e["ev"] == "fire"]:
        m = f["mint"]
        ours = next((e for e in ev if e["ev"] in ("buy_failed", "buy_land") and e.get("sig") == f["buy_sig"]), None)
        t_us = ours["t"] if ours else f["t_dump_rx"] + 300e6
        pd = S.pos(f["slot"], f["dump_sig"])
        if not pd: continue
        tape = [e for e in ev if e["ev"] == "tape" and e["mint"] == m and e["buy"] and e["user"] != W and f["t_dump_rx"] <= e["t"] <= t_us + 50e6]
        seen = set()
        for e in tape:
            if e["sig"] in seen: continue
            seen.add(e["sig"])
            t = S.rpc("getTransaction", [e["sig"], {"encoding": "json", "maxSupportedTransactionVersion": 0}])
            if not t: continue
            msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}
            keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
            cu_price = cu_limit = 0; tips = []
            for ix in msg["instructions"]:
                pr = keys[ix["programIdIndex"]]; d = S.b58dec(ix["data"])
                if pr == S.CB and d:
                    if d[0] == 3: cu_price = int.from_bytes(d[1:9], "little")
                    elif d[0] == 2: cu_limit = int.from_bytes(d[1:5], "little")
                elif pr == S.SYS and len(d) >= 12 and int.from_bytes(d[:4], "little") == 2:
                    to = keys[ix["accounts"][1]]
                    if to in S.TIP: tips.append((S.TIP[to], int.from_bytes(d[4:12], "little")))
            pb = S.pos(t["slot"], e["sig"])
            if not pb: continue
            ms = (t["slot"] - f["slot"]) * S.SLOT_MS + (pb[0] / pb[1] - pd[0] / pd[1]) * S.SLOT_MS
            rows.append(dict(client=S.leader_client(t["slot"]), user=e["user"][:8], ms=round(ms, 1), dslot=t["slot"] - f["slot"], ahead=e["t"] < t_us,
                             prio_sol=cu_price * (cu_limit or 200000) / 1e15, cu_price=cu_price, cu_limit=cu_limit,
                             tips=tips, tip_sol=sum(x for _, x in tips) / 1e9, cu_used=t["meta"].get("computeUnitsConsumed"), sol=e["sol"] / 1e9))
json.dump(rows, open("/home/moiz/sniper/ops/dip/speed/fast_bots_paths.json", "w"), indent=1)
for r in sorted(rows, key=lambda r: (r["client"], r["ms"])):
    tp = ", ".join(f"{s} {x / 1e9:.4f}" for s, x in r["tips"]) or "no tip"
    print(f"{r['client']:9s} {'AHEAD' if r['ahead'] else 'after'} {r['user']} {r['ms']:6.1f} ms +{r['dslot']} | prio {r['prio_sol']:.5f} SOL (price {r['cu_price']:,} uL x {r['cu_limit']:,} CU, used {r['cu_used']}) | {tp} | buy {r['sol']:.2f}")
print()
for c in sorted({r["client"] for r in rows}):
    a = [r for r in rows if r["client"] == c and r["ms"] <= 60]
    if not a: continue
    svc = collections.Counter(s for r in a for s, _ in r["tips"]) + collections.Counter("no tip" for r in a if not r["tips"])
    print(f"{c}: {len(a)} buys within 60 ms of the dump | priority median {statistics.median(r['prio_sol'] for r in a):.5f} SOL, CU price median {statistics.median(r['cu_price'] for r in a):,.0f} uL | tip median {statistics.median(r['tip_sol'] for r in a):.4f} | paths {dict(svc)}")
