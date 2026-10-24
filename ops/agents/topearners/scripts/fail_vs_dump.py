# where do each wallet's FAILED buy-intent txs land relative to the nearest >=1 SOL sell on the same mint?
# (failed BEFORE the dump in the same slot = the tx was sent before the dump executed -> pre-positioned / predictive)
import json, gzip, collections, sys, bisect
B = "/home/moiz/sniper/ops/agents/topearners/work/"
TOP = [l.strip() for l in open(B + sys.argv[1]) if l.strip()]
dumps = collections.defaultdict(list)
for line in gzip.open(B + "races.jsonl.gz", "rt"):
    r = json.loads(line); dumps[r["m"]].append((r["s"], r["i"], r["sol"], r["user"]))
for m in dumps: dumps[m].sort()
res = {w: collections.Counter() for w in TOP}; ec = {w: collections.defaultdict(collections.Counter) for w in TOP}
for line in gzip.open(B + "txrows.jsonl.gz", "rt"):
    x = json.loads(line)
    w = x["w"]
    if w not in res or x["kind"] not in ("buy", "unk") or not x["mints"]: continue
    D = dumps.get(x["mints"][0])
    tag = "ok" if x["ok"] else "fail"
    if not D: res[w][(tag, "no-dump-on-mint")] += 1; continue
    k = bisect.bisect_left(D, (x["s"], x["i"]))
    prev = D[k - 1] if k > 0 else None; nxt = D[k] if k < len(D) else None
    if prev and x["s"] - prev[0] <= 5 and prev[3] != w: cat = f"after(ds={min(x['s'] - prev[0], 2)})"
    elif nxt and nxt[0] - x["s"] <= 2 and nxt[3] != w: cat = f"BEFORE(ds={nxt[0] - x['s']})"
    else: cat = "no-dump-near"
    res[w][(tag, cat)] += 1
    if not x["ok"]: ec[w][cat][str(x["ec"])] += 1
for w in TOP:
    c = res[w]
    print(w[:10], {f"{k[0]}:{k[1]}": v for k, v in sorted(c.items())})
    for cat, cc in ec[w].items():
        if sum(cc.values()) > 50: print("      fail", cat, cc.most_common(4))
