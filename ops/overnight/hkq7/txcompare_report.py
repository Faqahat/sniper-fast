import json, statistics, collections
P = json.load(open("txcompare.json")); med = lambda v: statistics.median(v) if v else float("nan")
def row(x, tag):
    return (f"{tag:5s} {x['signer'][:6]} {x['ms']:6.1f}ms {x['leader_client']:9s} v{x['version']:6s} alt{x['alt']} {x['bytes']:4d}B sig{x['nsig']} keys{x['nkeys']:2d} ix{x['nix']} "
            f"ata{'Y' if x['ata'] else 'n'} nonce{'Y' if x['nonce'] else 'n'} | CU lim {x['cu_limit']:7d} used {x['cu_used'] or 0:6d} price {x['cu_price']:8d} | prio {x['prio_lam']/1e9:.5f} "
            f"tip {x['tip_lam']/1e9:.5f} {x['tip_svc'][:22]:22s} ({x['tip_where']}) | {x['buy']}")
for o in ("REVERT", "FILL"):
    v = [p for p in P if p["outcome"] == o]
    print(f"\n################ {o}S: {len(v)} (ours vs {'the buy that crossed our guard' if o == 'REVERT' else 'the rival ahead of us / right behind us'})")
    for p in sorted(v, key=lambda p: (p["wallet"], p["ours"]["slot"])):
        print(f"--- {p['wallet']} {p['ours']['mint'][:6]} dump {p['dump_sol']:.2f} SOL on {p['ours']['dump_client']} | rival {p['role']} | buys between dump and us: {p['n_ahead']}")
        print("   " + row(p["ours"], "OURS")); print("   " + row(p["rival"], "RIVAL"))
    for side in ("ours", "rival"):
        X = [p[side] for p in v]
        if not X: continue
        c = lambda k: collections.Counter(str(x[k]) for x in X).most_common(4)
        print(f"  {side.upper():5s} median: {med([x['ms'] for x in X]):5.1f} ms after dump | bytes {med([x['bytes'] for x in X]):.0f} | keys {med([x['nkeys'] for x in X]):.0f} | ix {med([x['nix'] for x in X]):.0f} | "
              f"CU limit {med([x['cu_limit'] for x in X]):.0f} used {med([x['cu_used'] or 0 for x in X]):.0f} price {med([x['cu_price'] for x in X]):.0f} µlam | prio {med([x['prio_lam'] for x in X])/1e9:.5f} | "
              f"tip {med([x['tip_lam'] for x in X])/1e9:.5f} | fee paid {med([x['fee'] for x in X])/1e9:.5f}")
        print(f"        ALT {c('alt')} | version {c('version')} | ATA in tx {c('ata')} | nonce {c('nonce')} | buy {c('buy')} | tip where {c('tip_where')}")
        print(f"        tip services {collections.Counter(s for x in X for s in x['tip_svc'].split('+')).most_common(8)}")
    r = [p for p in v]
    if r:
        print(f"  rival faster in {sum(p['rival']['ms'] < p['ours']['ms'] for p in r)}/{len(r)} | rival higher CU price {sum(p['rival']['cu_price'] > p['ours']['cu_price'] for p in r)}/{len(r)} | "
              f"rival higher tip {sum(p['rival']['tip_lam'] > p['ours']['tip_lam'] for p in r)}/{len(r)} | rival smaller tx {sum(p['rival']['bytes'] < p['ours']['bytes'] for p in r)}/{len(r)} | "
              f"rival lower CU limit {sum(p['rival']['cu_limit'] < p['ours']['cu_limit'] for p in r)}/{len(r)}")
        same = [p for p in r if p["rival"]["slot"] == p["ours"]["slot"]]
        print(f"  same block as rival: {len(same)}/{len(r)} | there rival index earlier {sum(p['rival']['idx'] < p['ours']['idx'] for p in same)}/{len(same)}; "
              f"of those rival paid MORE prio {sum(p['rival']['idx'] < p['ours']['idx'] and p['rival']['prio_lam'] > p['ours']['prio_lam'] for p in same)}, MORE tip {sum(p['rival']['idx'] < p['ours']['idx'] and p['rival']['tip_lam'] > p['ours']['tip_lam'] for p in same)}")
