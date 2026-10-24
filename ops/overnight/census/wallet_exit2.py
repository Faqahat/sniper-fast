#!/usr/bin/env python3
# What sell sets off a wallet's exit? For each of its dip round trips whose exit comes right after someone else's sell:
# that sell's size, its rank among sells since entry (first / later), price vs entry and vs the peak at that moment; plus the
# same stats for the other sells during the hold that it did NOT react to. Local data only.  usage: WALLET=... python3 -I wallet_exit2.py
import sys, os, json, gzip, glob, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry"); os.environ["RP_REPAIR"] = "0"
import rp
from multiprocessing import Pool
U = os.environ["WALLET"]
ms = set()
for f in glob.glob("/home/moiz/sniper/ops/overnight/census/parts/*.jsonl.gz"):
    for l in gzip.open(f, "rt"):
        if l[2:10] == U[:8]: ms.add(json.loads(l)[1])
L = rp.load_launches()
byb = collections.defaultdict(set)
for m in ms: byb[(L[m]["run"], rp.bucket(m))].add(m)
def work(key):
    run, b = key; react = []; ignore = []
    for m, tr in rp.read_bucket(run, b, byb[key]).items():
        mine = [k for k, t in enumerate(tr) if t["user"] == U]
        for k in mine:
            t = tr[k]
            if not t["buy"] or k == 0 or tr[k - 1]["buy"] or tr[k - 1]["sol"] < 1e9: continue
            ks = next((j for j in mine if j > k and not tr[j]["buy"]), None)
            if ks is None: continue
            px = lambda z: z["vsol"] / z["vtok"]; p_in = px(t); peak = p_in; nsell = 0
            for j in range(k + 1, ks):
                z = tr[j]
                if not z["buy"] and z["user"] != U:
                    nsell += 1
                    pre = (z["vsol"] + z["sol"]) / (z["vtok"] - z["tok"])
                    rec = dict(sol=z["sol"] / 1e9, rank=nsell, up=pre / p_in, dd=px(z) / peak, drop=px(z) / pre, slots=z["s"] - t["s"])
                    (react if j == ks - 1 else ignore).append(rec)
                peak = max(peak, px(z))
    return react, ignore
if __name__ == "__main__":
    RE = []; IG = []
    with Pool(4) as p:
        for a, b in p.imap_unordered(work, sorted(byb)): RE += a; IG += b
    def d(v, name):
        if not v: return
        q = lambda f: statistics.median(f(r) for r in v)
        print(f"  {name}: n {len(v)} | sell size median {q(lambda r: r['sol']):.3f} SOL, >=0.5 SOL {sum(1 for r in v if r['sol'] >= 0.5) / len(v):.0%}, >=1 SOL {sum(1 for r in v if r['sol'] >= 1) / len(v):.0%}"
              f" | first sell since entry {sum(1 for r in v if r['rank'] == 1) / len(v):.0%} | price before it vs entry {q(lambda r: r['up']):.3f}"
              f" | after it vs peak {q(lambda r: r['dd']):.3f} | its own drop {q(lambda r: r['drop']):.3f} | slots since entry {q(lambda r: r['slots']):.0f}")
    print(U[:8], "exits right after another wallet's sell:")
    d(RE, "sells it REACTED to")
    d(IG, "sells it did NOT react to")
    for lo, hi in ((0, 0.2), (0.2, 0.5), (0.5, 1), (1, 3), (3, 1000)):
        a = sum(1 for r in RE if lo <= r["sol"] < hi); b = sum(1 for r in IG if lo <= r["sol"] < hi)
        print(f"    sell size {lo}-{hi} SOL: it reacted to {a} of {a + b} ({a / max(a + b, 1):.0%})")
    for lo, hi in ((0, 0.9), (0.9, 0.95), (0.95, 0.98), (0.98, 1.01)):
        a = sum(1 for r in RE if lo <= r["dd"] < hi); b = sum(1 for r in IG if lo <= r["dd"] < hi)
        print(f"    price after the sell vs peak {lo}-{hi}: reacted {a} of {a + b} ({a / max(a + b, 1):.0%})")
