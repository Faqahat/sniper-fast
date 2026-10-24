#!/usr/bin/env python3
# What happens right before a wallet's SELLS and BUYS (all of them, not only the first buy)? Reactive pattern check vs a
# baseline of random trades in the same launches.  usage: python3 -I sellctx.py <wallet prefix>
import sys, os, json, gzip, glob, collections, statistics, random
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry"); os.environ["RP_REPAIR"] = "0"
import rp
from multiprocessing import Pool
WP = sys.argv[1]
ms = set(); U = None
for f in glob.glob("/home/moiz/sniper/ops/overnight/census/parts/*.jsonl.gz"):
    for l in gzip.open(f, "rt"):
        if l[2:2 + len(WP)] == WP: r = json.loads(l); ms.add(r[1]); U = r[0]
L = rp.load_launches()
byb = collections.defaultdict(set)
for m in ms: byb[(L[m]["run"], rp.bucket(m))].add(m)
def cls(t, same):
    if t is None: return "none"
    sz = t["sol"] / 1e9; b = "B" if t["buy"] else "S"
    return f"{b}{'>=1' if sz >= 1 else ('0.3-1' if sz >= 0.3 else '<0.3')}{'' if same else '(prev slot)'}"
def work(key):
    run, b = key; out = collections.Counter(); base = collections.Counter(); rnd = random.Random(b)
    gaps = collections.Counter(); moves = []
    tra = rp.read_bucket(run, b, byb[key])
    for m, tr in tra.items():
        for k, t in enumerate(tr):
            if k == 0: continue
            p = tr[k - 1]; same = p["s"] == t["s"]
            if t["user"] == U:
                out[("SELL " if not t["buy"] else "BUY  ") + cls(p, same)] += 1
                if not t["buy"]:
                    # price move from our wallet's last buy to the trade before this sell
                    pass
            elif rnd.random() < 0.05:
                base[("sell " if not t["buy"] else "buy  ") + cls(p, same)] += 1
    return out, base
if __name__ == "__main__":
    O = collections.Counter(); Bc = collections.Counter()
    with Pool(8) as p:
        for o, bb in p.imap_unordered(work, sorted(byb)): O.update(o); Bc.update(bb)
    for side in ("BUY  ", "SELL "):
        tot = sum(v for k, v in O.items() if k.startswith(side)); btot = sum(v for k, v in Bc.items() if k.startswith(side.lower()))
        print(f"\n{U[:8]} {side.strip()}s: {tot} — preceding trade (share)   vs random {side.strip().lower()}s in the same launches")
        for k, v in sorted(((k, v) for k, v in O.items() if k.startswith(side)), key=lambda kv: -kv[1])[:10]:
            bk = side.lower() + k[len(side):]
            print(f"   {k[len(side):]:22s} {v / tot:6.1%}   baseline {Bc.get(bk, 0) / max(btot, 1):6.1%}")
