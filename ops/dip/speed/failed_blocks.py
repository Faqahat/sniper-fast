#!/usr/bin/env python3
# Owner 10-24 17:55 PKT: "check our competitors in the blocks we failed in, last few failed txns: how did they land" (do higher
# tips / fees put them ahead of us?). For every failed fire of the given run records: all txs on that mint in the dump slot S and
# S+1 from the collector's raw chunks (failed txs included), in block order: who, buy / sell, SOL, priority (micro-lamports per
# CU), tips (relay via tipmap), ok / error; the dump and OUR tx marked. Then the buys that landed between the dump and us, vs us.
# usage: python3 -I failed_blocks.py dip_r9.jsonl [more.jsonl ...]
import json, gzip, os, sys, collections, statistics
TX = "/home/moiz/sniper-data/collect/run_20261023_1426/txs"
TIP = json.load(open("/home/moiz/sniper/ops/agents/tipmap.json"))
US = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
chunks = sorted(int(f.split("_")[1].split(".")[0]) for f in os.listdir(TX))
def lines_for(t):
    out = []
    for c in chunks:
        if c - 300 <= t <= c + 330:
            try:
                for l in gzip.open(f"{TX}/txs_{c}.jsonl.gz", "rt"): out.append(l)
            except (EOFError, OSError): pass
    return out
def side(r):
    ix = " ".join(r.get("ixn") or [])
    return "BUY " if "Buy" in ix else ("SELL" if "Sell" in ix else "----")
def tips(r):
    t = r.get("tips") or []
    return [(TIP.get(a, "?" + a[:4]), int(l)) for a, l in t]
agg = collections.defaultdict(list); summary = []
for f in sys.argv[1:]:
    ev = [json.loads(l) for l in open(f)]
    land = {e["sig"] for e in ev if e["ev"] == "buy_land"}
    for fire in [e for e in ev if e["ev"] == "fire" and e["buy_sig"] not in land]:
        m, S = fire["mint"], fire["slot"]; t = fire["t_dump_rx"] // 10**9
        rows = []
        for l in lines_for(t):
            if m not in l: continue
            r = json.loads(l); s = int(r["s"])
            if s in (S, S + 1) and m in (r.get("mints") or []): rows.append(r)
        rows.sort(key=lambda r: (int(r["s"]), int(r["i"])))
        seen = set(); rows = [r for r in rows if not (r["sig"] in seen or seen.add(r["sig"]))]
        ki = next((k for k, r in enumerate(rows) if r["sig"] == fire["dump_sig"]), None)
        ko = next((k for k, r in enumerate(rows) if r["sig"] == fire["buy_sig"]), None)
        print(f"\n=== {os.path.basename(f)[:-6]} {m[:8]} dump slot {S} leader {fire['client']} route {fire['route']}")
        if ki is None or ko is None: print("   dump or our tx not in the recorded chunks"); continue
        for k, r in enumerate(rows):
            if k < ki or k > ko + 2: continue
            who = (r.get("signers") or ["?"])[0]
            sol = abs(int(next((d for a, d in (r.get("sd") or []) if a == who), 0))) / 1e9
            tag = "<< DUMP" if k == ki else ("<< US" if k == ko else "")
            ok = "ok " if not r.get("err") or r.get("err") == "None" else "ERR"
            tp = ", ".join(f"{n} {l / 1e9:.4f}" for n, l in tips(r)) or "no tip"
            print(f"   slot +{int(r['s']) - S} idx {int(r['i']):4d} {side(r)} {ok} {who[:8]} {sol:7.3f} SOL  prio {int(r.get('cup') or 0) / 1e6:5.2f}M  {tp:34s} {tag}")
            if ki < k < ko and side(r) == "BUY " and ok == "ok " and who not in US:
                agg["ahead"].append(dict(cup=int(r.get("cup") or 0), tip=sum(l for _, l in tips(r)), relays=[n for n, _ in tips(r)]))
        us = rows[ko]; agg["us"].append(dict(cup=int(us.get("cup") or 0), tip=sum(l for _, l in tips(us))))
        summary.append((m[:8], int(rows[ko]["s"]) - S, int(rows[ko]["i"]), sum(1 for r in rows[ki + 1:ko] if side(r) == "BUY " and (not r.get("err") or r.get("err") == "None"))))
A, U = agg["ahead"], agg["us"]
print(f"\n=== {len(summary)} failed buys; successful rival buys that landed between the dump and us: {len(A)}")
if A and U:
    ucup = statistics.median(x["cup"] for x in U); utip = statistics.median(x["tip"] for x in U)
    print(f"   our priority median {ucup / 1e6:.2f}M uL/CU, our tips in the tx median {utip / 1e9:.4f} SOL")
    print(f"   rivals ahead: priority median {statistics.median(x['cup'] for x in A) / 1e6:.2f}M; paid MORE priority than us: {sum(1 for x in A if x['cup'] > ucup)}/{len(A)}")
    print(f"   rivals ahead: tip median {statistics.median(x['tip'] for x in A) / 1e9:.4f} SOL; no tip {sum(1 for x in A if x['tip'] == 0)}/{len(A)}; tipped MORE than us: {sum(1 for x in A if x['tip'] > utip)}/{len(A)}; tipped > 0.001: {sum(1 for x in A if x['tip'] > 1_000_000)}/{len(A)}")
    rel = collections.Counter(r for x in A for r in x["relays"]) ; print("   relays used by rivals ahead:", dict(rel.most_common()))
