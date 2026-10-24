import sys, json, gzip, collections, statistics
rows = []
with gzip.open("fwd2.jsonl.gz", "rt") as f:
    meta = json.loads(f.readline()); NAMES = meta["rules"]
    for l in f: rows.append(json.loads(l))
rows.sort(key=lambda r: r["bt"] or 0); mid = rows[0]["bt"] + (rows[-1]["bt"] - rows[0]["bt"]) / 2
LS = json.load(open("lists_cut1709.json"))
U = lambda r: any(LS.get(w, {}).get(r["signer"], 0) >= 1 for w in ("9Sh2fd", "DGmspi"))
i = NAMES.index("eos1")
R = [r for r in rows if U(r)]
g = collections.defaultdict(list)
for r in R: g[r["signer"]].append(r)
print(f"copy-list launches {len(R)} from {len(g)} deployers; per deployer eos1 PnL (SOL) at L35 / L60 / L75, halves at L60")
for d, v in sorted(g.items(), key=lambda kv: -len(kv[1]))[:30]:
    f = lambda c: sum(r["cfg"][c]["pnl"][i] for r in v if c in r["cfg"])
    h1 = sum(r["cfg"]["L60"]["pnl"][i] for r in v if "L60" in r["cfg"] and r["bt"] < mid); h2 = f("L60") - h1
    w9 = LS.get("9Sh2fd", {}).get(d, 0); wd = LS.get("DGmspi", {}).get(d, 0)
    print(f"   {d[:8]} n {len(v):3} | L35 {f('L35'):+6.2f} L60 {f('L60'):+6.2f} L75 {f('L75'):+6.2f} | L60 halves {h1:+.2f}/{h2:+.2f} | pre-window attempts 9Sh {w9} DGm {wd} | dev_buy med {statistics.median(r['dev_buy'] for r in v):.2f} glued med {statistics.median(r['glued_n'] for r in v)}")
# create-slot crowd: how many outside buys landed in the first 2 slots, vs eos1 pnl at L60
print("\nby number of outside txs our engine saw within 100 ms (crowd), copy-list, eos1:")
for lo, hi in ((0, 1), (1, 3), (3, 6), (6, 10), (10, 99)):
    v = [r for r in R if lo <= r["cfg"].get("L90", {}).get("ahead", 0) < hi]
    if v: print(f"   ahead@90ms {lo}-{hi - 1}: n {len(v):3}  L35 {sum(r['cfg']['L35']['pnl'][i] for r in v if 'L35' in r['cfg']):+.2f}  L60 {sum(r['cfg']['L60']['pnl'][i] for r in v if 'L60' in r['cfg']):+.2f}  L75 {sum(r['cfg']['L75']['pnl'][i] for r in v if 'L75' in r['cfg']):+.2f}")
