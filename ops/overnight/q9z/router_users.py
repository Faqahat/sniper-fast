#!/usr/bin/env python3
# READ-ONLY, offline: who else signs txs that call 9qz7cW's router program 2eFuLSK4 (or send to the b1oo recipients)?
# Scans the collector's raw txs (both runs). -> router_users.json
import os, json, gzip, glob, zlib, collections
from multiprocessing import Pool
D = "/home/moiz/sniper-data/collect"; HERE = os.path.dirname(os.path.abspath(__file__))
KEYS = {"2eFuLSK4McKonBcB6XLax8gSgxwR56zNfrjHsvkNkftj": "router", "b1ooMngj7WbNPMZpWpnYRjxQ96RcDZ9ZFpRfjw1g7tg": "b1ooMngj", "b1oomst2baE3FqxFPHaA9JwhXgFG9HdTLmbNKDen1kK": "b1oomst2",
        "5nUdEsBkw2EcFeAVRzkQjZFohQALawct5d9BKy3wuiNR": "nonce1", "895KeyJjjoZcbkQELHp28dTgQtJBxXH53aND9GffSPK4": "nonce2", "CMXoxdGUWB55pHxJHSaRwGWRCwjqREKxMgYMxK9NBJn9": "nonce3", "DgGakg9ZdUvydA3KLbSuNo4wv3P9YGsgyuyvg4uqNBkk": "nonce4"}
def work(f):
    c = collections.Counter()
    try:
        for line in gzip.open(f, "rt"):
            hit = [v for k, v in KEYS.items() if k in line]
            if not hit: continue
            r = json.loads(line); s = (r.get("signers") or ["?"])[0]
            for h in hit: c[(h, s)] += 1
    except (EOFError, OSError, zlib.error): pass
    return c
if __name__ == "__main__":
    files = sorted(glob.glob(os.path.join(D, "run_20261021_2207", "txs", "*.jsonl.gz"))) + sorted(glob.glob(os.path.join(D, "run_20261022_1543", "txs", "*.jsonl.gz")))
    tot = collections.Counter()
    with Pool(8) as p:
        for c in p.imap_unordered(work, files): tot.update(c)
    by = collections.defaultdict(dict)
    for (h, s), n in tot.items(): by[h][s] = n
    json.dump(by, open(os.path.join(HERE, "router_users.json"), "w"))
    for h, d in by.items():
        print(h, "signers", len(d), sorted(d.items(), key=lambda kv: -kv[1])[:6])
