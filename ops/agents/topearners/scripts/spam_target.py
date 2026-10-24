# do spam windows target a specific big buyer's dump? compare the wallet whose >=1 SOL buy preceded the window with the seller
# of the dump the spammer filled after.
import os, sys, json, gzip, collections
os.environ["RP_PHASEA_R2"] = "phaseA_selfwd"; os.environ["RP_PHASEA_R3"] = "phaseA_r3day"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
B = "/home/moiz/sniper/ops/agents/topearners/work/"
W = sys.argv[1]
L = collections.defaultdict(list)
for f in (B + "txrows.jsonl.gz", B + "txrows2.jsonl.gz"):
    for line in gzip.open(f, "rt"):
        x = json.loads(line)
        if x["w"] == W and x["mints"]: L[x["mints"][0]].append(x)
launch = rp.load_launches()
byb = collections.defaultdict(set)
for m, X in L.items():
    if m in launch and any(x["ok"] and x["kind"] == "buy" for x in X): byb[(launch[m]["run"], rp.bucket(m))].add(m)
c = collections.Counter(); hold_win = []
for (run, b), ms in byb.items():
    tr = rp.read_bucket(run, b, ms)
    for m in ms:
        T = tr.get(m) or []
        X = sorted(L[m], key=lambda x: (x["s"], x["i"]))
        s0, i0 = X[0]["s"], X[0]["i"]
        prev = [t for t in T if (t["s"], t["i"]) < (s0, i0) and s0 - t["s"] <= 3 and t["buy"] and t["sol"] >= 1e9]
        f = next(x for x in X if x["ok"] and x["kind"] == "buy")
        dump = [t for t in T if not t["buy"] and t["sol"] >= 1e9 and (t["s"], t["i"]) < (f["s"], f["i"]) and f["s"] - t["s"] <= 2]
        if not prev or not dump: c["n/a"] += 1; continue
        opener = prev[-1]["user"]; seller = dump[-1]["user"]
        creator = launch[m].get("creator")
        c["seller==window-opener" if seller == opener else ("seller==creator" if seller == creator else "other seller")] += 1
print(W[:10], dict(c))
