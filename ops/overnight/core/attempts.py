#!/usr/bin/env python3
# READ-ONLY, offline: for every launch in the two collector runs, which of the 3 case-study wallets ATTEMPTED it
# (successful buy = TradeEvent with user=wallet; failed attempt = failed tx signed by the wallet touching the mint),
# with chain position (slot offset from the create, index). Output: attempts.json {mint: {wallet6: [ok, slot_off, idx, sol]}}
import sys, os, json, gzip, glob, collections
from multiprocessing import Pool
D = "/home/moiz/sniper-data/collect"; RUNS = ["run_20261021_2207", "run_20261022_1543"]
W = {"9Sh2fdqMQcec7W9LzzfvkYphrdyR3S8aUBsKdv9xNYa1": "9Sh2fd", "DGmspiBs2ePJ7WgN1pyX5RJDpzhyxYrBN1P4bXNC1NR3": "DGmspi", "D24ipYXuDt6PXEPV6rZqfWb35WJaTJW3gDoXwt7yJCwQ": "D24ipY"}
L = {}
for r in RUNS:
    for l in open(os.path.join(D, r, "launches.jsonl")):
        try: c = json.loads(l)
        except Exception: continue
        L.setdefault(c["mint"], c)
def work(bdir):
    out = collections.defaultdict(dict)
    for f in glob.glob(os.path.join(bdir, "*.jsonl.gz")):
        try:
            for line in gzip.open(f, "rt"):
                if not any(w[:10] in line for w in W): continue
                r = json.loads(line); m = r[1]; c = L.get(m)
                if not c: continue
                if r[0] == "T":
                    user, buy, sol = r[14], r[15], r[16]
                    if user in W and buy == 1 and r[12] == 0: out[m].setdefault(W[user], [1, r[2] - c["slot"], r[3], sol / 1e9])
                else:
                    signer, err = r[6], r[12]
                    if signer in W and err == 1: out[m].setdefault(W[signer], [0, r[2] - c["slot"], r[3], 0])
        except (EOFError, OSError): pass
    return dict(out)
if __name__ == "__main__":
    dirs = sorted(glob.glob(os.path.join(D, "phaseA", "b*"))) + sorted(glob.glob(os.path.join(D, os.environ.get("RP_PHASEA_R2", "phaseA_fwd"), "b*")))
    res = {}
    with Pool(14) as p:
        for o in p.imap_unordered(work, dirs):
            for m, v in o.items(): res.setdefault(m, {}).update(v)
    json.dump(res, open(os.environ.get("ATTEMPTS_OUT", "/home/moiz/sniper/ops/overnight/core/attempts.json"), "w"))
    cnt = collections.Counter(w for v in res.values() for w in v); ok = collections.Counter(w for v in res.values() for w, a in v.items() if a[0])
    print("launches attempted:", len(res), "| per wallet attempts:", dict(cnt), "| successful buys:", dict(ok))
