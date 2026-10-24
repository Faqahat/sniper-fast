# do top wallets route by leader client? relay share per leader client (R2 slots, successful buys); and failed-sell timing
import json, gzip, collections, sys
B = "/home/moiz/sniper/ops/agents/topearners/work/"
TOP = [l.strip() for l in open(B + sys.argv[1]) if l.strip()]
LB = json.load(open("/home/moiz/sniper/ops/overnight/dipshadow/leaders_book.json")); LEAD = LB["leaders"]; NODES = LB["nodes"]
ct = {w: collections.defaultdict(collections.Counter) for w in TOP}
cupc = {w: collections.defaultdict(list) for w in TOP}
own = collections.defaultdict(lambda: collections.defaultdict(list))
fsell = collections.defaultdict(list)
for line in gzip.open(B + "txrows.jsonl.gz", "rt"):
    x = json.loads(line); w = x["w"]
    if w not in ct: continue
    if x["mints"]: own[w][x["mints"][0]].append((x["s"], x["i"], x["kind"], x["ok"]))
    if x["kind"] != "buy" or not x["ok"]: continue
    ld = LEAD.get(str(x["s"]))
    if not ld: continue
    cls = NODES.get(ld, {}).get("client", "?")
    rel = "+".join(sorted(set(t[0] for t in x["tips"]))) or "(none)"
    ct[w][cls][rel] += 1
for w in TOP:
    print("=" * 10, w[:10])
    for cls in ("AgaveBam", "JitoLabs", "HarmonicAgave", "Firedancer", "HarmonicFiredancer"):
        c = ct[w][cls]; n = sum(c.values())
        if n >= 50: print(f"   {cls:18s} n={n:5d} " + "  ".join(f"{k}:{v/n:.2f}" for k, v in c.most_common(5)))
# failed sells: relative to own ok buy on the same mint
for w in TOP:
    cnt = collections.Counter()
    for m, L in own[w].items():
        L.sort()
        buys = [(s, i) for s, i, k, ok in L if k == "buy" and ok]
        sells_ok = [(s, i) for s, i, k, ok in L if k == "sell" and ok]
        for s, i, k, ok in L:
            if k != "sell" or ok: continue
            if not buys: cnt["no-ok-buy-on-mint"] += 1; continue
            if (s, i) < buys[0]: cnt["before-first-buy"] += 1
            elif sells_ok and (s, i) > sells_ok[-1]: cnt["after-last-ok-sell"] += 1
            else: cnt["between-buy-and-sell"] += 1
    if sum(cnt.values()) > 100: print(w[:10], "failed sells:", dict(cnt))
