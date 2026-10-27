#!/usr/bin/env python3
"""CLIENTS study: Rakurai attempts in detail (MEASURED from chain_txs.json + attempts.csv).
For each Rakurai attempt: the dump's block, txs on the same mint after the dump (same slot and next slot), their paths (tip labels),
CU price / limit, and where our buy landed."""
import csv, json, collections, sys
A = "/home/moiz/sniper-data/speed_truth/attempts.csv"
want = sys.argv[1] if len(sys.argv) > 1 else "Rakurai"
rows = [r for r in csv.DictReader(open(A)) if r["client"] == want]
C = json.load(open("/home/moiz/sniper-data/speed_truth/chain_txs.json"))
SS = json.load(open("/home/moiz/sniper-data/speed_truth/slot_stats.json"))
by_slot = collections.defaultdict(list)
for t in C: by_slot[t["s"]].append(t)
for r in rows:
    ds, di = int(r["dump_slot"]), int(r["dump_idx"]); os_, oi = int(r["our_slot"]), int(r["our_idx"])
    print(f"\n### {r['time_pkt']} {r['server']} r{r['run']} {r['result']} turn_slot={r['turn_slot']} path={r['landed_path']} dump {ds}/{di} (block n={r['dump_block_n']}, slot_stats={SS.get(str(ds))}) -> ours {os_}/{oi} (slot_stats={SS.get(str(os_))}) land_feed={r['land_feed_ms']} seen={r['our_tx_seen_ms']}")
    for s in (ds, ds + 1) if os_ > ds else (ds,):
        txs = sorted([t for t in by_slot[s] if r["mint"] in t.get("mints", [])], key=lambda t: t["i"])
        for t in txs:
            if s == ds and t["i"] < di: continue
            if s == os_ and t["i"] > oi + 5: break
            tips = ",".join(f"{a}:{b/1e9:.4f}" for a, b in t.get("tips", [])) or "-"
            kind = "OURS" if t.get("ours") else ("DUMP" if t["sig"] == r["dump_sig"] else "")
            trs = t.get("tr") or []
            side = ("buy" if trs and trs[0].get("buy") else "sell" if trs else "-")
            print(f"   s+{s-ds} i={t['i']:4d} {kind:4s} {t['signer'][:8]} {side:4s} err={'Y' if t['err'] else 'n'} cup={t.get('cup')} cul={t.get('cul')} cu={t.get('cu')} tips={tips} ixn={'/'.join((t.get('ixn') or [])[:4])}")
