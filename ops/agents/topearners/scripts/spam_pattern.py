# how the pre-positioned spammers spam: per mint, txs per slot, duration, start/stop relative to their fill & the dump
import json, gzip, collections, sys, statistics
B = "/home/moiz/sniper/ops/agents/topearners/work/"
W = [l.strip() for l in open(B + sys.argv[1]) if l.strip()]
rows = collections.defaultdict(lambda: collections.defaultdict(list))
for line in gzip.open(B + "txrows.jsonl.gz", "rt"):
    x = json.loads(line)
    if x["w"] in W and x["mints"]: rows[x["w"]][x["mints"][0]].append(x)
for w in W:
    M = rows[w]
    nm = len(M); per = []; spans = []; rate = []; okm = 0; sameslot = []
    for m, L in M.items():
        L.sort(key=lambda x: (x["s"], x["i"]))
        n = len(L); span = L[-1]["s"] - L[0]["s"] + 1
        per.append(n); spans.append(span); rate.append(n / span)
        if any(x["ok"] and x["kind"] == "buy" for x in L): okm += 1
        c = collections.Counter(x["s"] for x in L); sameslot.append(max(c.values()))
    tot = sum(per)
    allslots = collections.Counter(x["s"] for L in M.values() for x in L)
    print(f"{w[:10]} mints={nm} txs={tot} mints_with_fill={okm} txs/mint p50={statistics.median(per):.0f} p90={sorted(per)[int(.9*len(per))]}  span(slots) p50={statistics.median(spans):.0f} p90={sorted(spans)[int(.9*len(spans))]}  txs/slot/mint p50={statistics.median(rate):.2f} max-in-one-slot p50={statistics.median(sameslot)} p90={sorted(sameslot)[int(.9*len(sameslot))]}  distinct slots={len(allslots)}")
