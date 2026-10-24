#!/usr/bin/env python3
# READ-ONLY: which relay landed each of haqqiUUX's txs (one tip per copy under a durable nonce -> the landed copy's tip names the
# winning relay), by the slot leader's client and distance from Frankfurt; tip amounts; CU price. "no tip" = its staked / tipless copy.
import sys, json, collections, statistics, importlib.util
spec = importlib.util.spec_from_file_location("osp", "/home/moiz/sniper/ops/speedcheck/our_speed.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
W = sys.argv[1] if len(sys.argv) > 1 else "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"; N = int(sys.argv[2]) if len(sys.argv) > 2 else 150
R = json.load(open("/home/moiz/sniper/ops/dip/speed/leaders/leader_rtt_new.json"))["leaders"]
sigs = [s for s in (S.rpc("getSignaturesForAddress", [W, {"limit": 1000}]) or []) if not s.get("err")][:N]
rows = []
for s in sigs:
    t = S.rpc("getTransaction", [s["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 0}])
    if not t: continue
    msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}; keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    tips = []; cup = 0
    for ix in msg["instructions"]:
        pr = keys[ix["programIdIndex"]]; d = S.b58dec(ix["data"])
        if pr == S.CB and d and d[0] == 3: cup = int.from_bytes(d[1:9], "little")
        if pr == S.SYS and len(d) >= 12 and int.from_bytes(d[:4], "little") == 2:
            to = keys[ix["accounts"][1]]
            if to in S.TIP: tips.append((S.TIP[to], int.from_bytes(d[4:12], "little")))
    client = S.leader_client(t["slot"]); ep = t["slot"] // 432000 * 432000; leader = S.LEAD.get(ep, {}).get(t["slot"])
    rtt = R.get(leader, {}).get("rtt") if leader else None
    svc = tips[0][0] if tips else "no tip"
    buy = any("Instruction: Buy" in l or "BuyExactQuoteIn" in l for l in (t["meta"].get("logMessages") or []))
    rows.append(dict(svc=svc, tip=sum(x for _, x in tips) / 1e9, client=client, rtt=rtt, cup=cup, buy=buy))
print(f"{W[:8]}: {len(rows)} successful txs")
for grp, sel in (("all", rows), ("buys", [r for r in rows if r["buy"]]), ("sells", [r for r in rows if not r["buy"]])):
    c = collections.Counter(r["svc"] for r in sel); print(f"  {grp:5s} n {len(sel):3d} winning relay: " + ", ".join(f"{k} {v} ({100 * v / max(1, len(sel)):.0f}%)" for k, v in c.most_common()))
print("  by leader client (winning relay counts):")
for cl in sorted({r["client"] for r in rows}):
    sel = [r for r in rows if r["client"] == cl]; c = collections.Counter(r["svc"] for r in sel)
    print(f"    {cl:10s} n {len(sel):3d}: " + ", ".join(f"{k} {v}" for k, v in c.most_common()))
near = lambda r: r["rtt"] is not None and r["rtt"] < 50
for lab, sel in (("nearby leaders (< 50 ms from Frankfurt)", [r for r in rows if near(r)]), ("far leaders", [r for r in rows if not near(r)])):
    c = collections.Counter(r["svc"] for r in sel); print(f"  {lab}: n {len(sel)}: " + ", ".join(f"{k} {v} ({100 * v / max(1, len(sel)):.0f}%)" for k, v in c.most_common()))
ht = [r["tip"] for r in rows if r["svc"] == "helius"]
if ht: print(f"  Helius tips: median {statistics.median(ht):.6f} SOL, min {min(ht):.6f}, max {max(ht):.6f} (<0.001 = SWQoS-only tier)")
print(f"  CU price median {statistics.median([r['cup'] for r in rows]):,} uL/CU")
