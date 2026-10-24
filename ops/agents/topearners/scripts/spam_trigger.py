# what starts a spammer's window on a mint? look at the tape just before its first tx on the mint
import os, sys, json, gzip, collections, statistics
os.environ["RP_PHASEA_R2"] = "phaseA_selfwd"; os.environ["RP_PHASEA_R3"] = "phaseA_r3day"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
B = "/home/moiz/sniper/ops/agents/topearners/work/"
W = sys.argv[1]
L = collections.defaultdict(list)
for line in gzip.open(B + "txrows.jsonl.gz", "rt"):
    x = json.loads(line)
    if x["w"] == W and x["mints"]: L[x["mints"][0]].append(x)
launch = rp.load_launches()
byb = collections.defaultdict(set)
for m in L:
    if m in launch: byb[(launch[m]["run"], rp.bucket(m))].add(m)
stat = collections.Counter(); lead = []; ages = []; fills = []
for (run, b), ms in list(byb.items())[:400]:
    tr = rp.read_bucket(run, b, ms)
    for m in ms:
        T = tr.get(m) or []
        X = sorted(L[m], key=lambda x: (x["s"], x["i"]))
        s0 = X[0]["s"]; i0 = X[0]["i"]
        prev = [t for t in T if (t["s"], t["i"]) < (s0, i0)]
        if not prev: stat["no-trade-before"] += 1; continue
        last = prev[-1]
        # biggest trade in the 3 slots before the window starts
        near = [t for t in prev if s0 - t["s"] <= 3]
        big = max(near, key=lambda t: t["sol"]) if near else None
        if big: stat[("big-before", "buy" if big["buy"] else "sell", "≥1SOL" if big["sol"] >= 1e9 else "<1SOL")] += 1
        else: stat["quiet-3-slots-before"] += 1
        ages.append(s0 - launch[m]["slot"])
        okb = [x for x in X if x["ok"] and x["kind"] == "buy"]
        if okb:
            f = okb[0]
            dumps_before = [t for t in T if not t["buy"] and t["sol"] >= 1e9 and (t["s"], t["i"]) < (f["s"], f["i"]) and f["s"] - t["s"] <= 2]
            fills.append((f["s"] - s0, len(dumps_before)))
print(W[:10], dict(stat))
print("  window start: token age (slots) p25/50/75 =", [sorted(ages)[int(p * len(ages))] for p in (.25, .5, .75)] if ages else None)
print("  fill after window start (slots) p25/50/75 =", [sorted(f[0] for f in fills)[int(p * len(fills))] for p in (.25, .5, .75)] if fills else None, " fills preceded by a >=1 SOL sell within 2 slots:", sum(1 for f in fills if f[1]), "/", len(fills))
