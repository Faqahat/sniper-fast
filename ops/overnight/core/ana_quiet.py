import sys, json, gzip, collections, statistics
rows = []
with gzip.open("fwd2.jsonl.gz", "rt") as f:
    meta = json.loads(f.readline()); NAMES = meta["rules"]
    for l in f: rows.append(json.loads(l))
rows.sort(key=lambda r: r["bt"] or 0); mid = rows[0]["bt"] + (rows[-1]["bt"] - rows[0]["bt"]) / 2
LS = json.load(open("lists_cut1709.json"))
U = lambda r: any(LS.get(w, {}).get(r["signer"], 0) >= 1 for w in ("9Sh2fd", "DGmspi"))
i = NAMES.index("eos1")
# walk-forward per-deployer contest rate: share of its earlier launches (any, not only list) with >=1 outside tx before 75 ms
hist = collections.defaultdict(list); sel = {}
for r in rows:
    h = hist[r["signer"]]
    sel[r["mint"]] = (statistics.mean(h) if len(h) >= 2 else None)
    if "L75" in r["cfg"]: h.append(1 if r["cfg"]["L75"]["ahead"] > 0 else 0)
for thr in (None, 0.75, 0.5, 0.34, 0.2):
    R = [r for r in rows if U(r) and (thr is None or (sel[r["mint"]] is not None and sel[r["mint"]] <= thr))]
    out = []
    for c in ("L35", "L60", "L75"):
        v = [r["cfg"][c]["pnl"][i] for r in R if c in r["cfg"]]; a = sum(r["cfg"][c]["pnl"][i] for r in R if c in r["cfg"] and r["bt"] < mid)
        out.append(f"{c} {sum(v):+6.2f} (halves {a:+.2f}/{sum(v) - a:+.2f}, mean {statistics.mean(v) if v else 0:+.4f})")
    print(f"contest-rate <= {thr}: n {len(R):3} | " + " | ".join(out))
