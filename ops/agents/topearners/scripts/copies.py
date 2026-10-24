# copies per decision: cluster each wallet's BUY-intent txs (ok + failed, incl. failed txs of its own program) by mint,
# a new cluster starts when the gap to the previous tx on that mint is > GAP slots.
import json, gzip, collections, sys
TOP = [l.strip() for l in open(sys.argv[1]) if l.strip()]
GAP = int(sys.argv[2]) if len(sys.argv) > 2 else 2
rows = collections.defaultdict(list)
for line in gzip.open("/home/moiz/sniper/ops/agents/topearners/work/txrows.jsonl.gz", "rt"):
    x = json.loads(line)
    if x["w"] in TOP and x["kind"] in ("buy", "unk") and x["mints"]: rows[x["w"]].append(x)
for w in TOP:
    R = rows[w]
    bym = collections.defaultdict(list)
    for x in R: bym[x["mints"][0]].append(x)
    clusters = []
    for m, L in bym.items():
        L.sort(key=lambda x: (x["s"], x["i"]))
        cur = [L[0]]
        for x in L[1:]:
            if x["s"] - cur[-1]["s"] > GAP: clusters.append(cur); cur = [x]
            else: cur.append(x)
        clusters.append(cur)
    size = collections.Counter(min(len(c), 6) for c in clusters)
    nok = collections.Counter(min(sum(1 for x in c if x["ok"]), 3) for c in clusters)
    # among clusters with >= 1 ok buy: how many extra txs, same slot?
    okc = [c for c in clusters if any(x["ok"] for x in c)]
    extra = collections.Counter(min(len(c) - 1, 5) for c in okc)
    same_slot = sum(1 for c in okc if len(c) > 1 and len(set(x["s"] for x in c)) == 1)
    multi_ok = sum(1 for c in okc if sum(1 for x in c if x["ok"]) > 1)
    relset = collections.Counter(len(set(t[0] for x in c if x["ok"] for t in x["tips"])) for c in okc)
    failc = [c for c in clusters if not any(x["ok"] for x in c)]
    fsize = collections.Counter(min(len(c), 6) for c in failc)
    # within-cluster fee/tip variation (different variants?)
    var = sum(1 for c in clusters if len(c) > 1 and len(set((x["cup"], tuple(t[0] for t in x["tips"])) for x in c)) > 1)
    print(f"{w[:10]} clusters={len(clusters)} with_ok={len(okc)} all_fail={len(failc)}")
    print(f"   size dist {dict(sorted(size.items()))}   ok-per-cluster {dict(sorted(nok.items()))}")
    print(f"   ok clusters: extra txs {dict(sorted(extra.items()))}  same-slot-multi={same_slot} multi_ok={multi_ok}  relays-in-ok {dict(relset)}")
    print(f"   all-fail cluster sizes {dict(sorted(fsize.items()))}   clusters with differing (cup,relay) variants: {var}")
