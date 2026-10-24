#!/usr/bin/env python3
# attempts (filled buy or failed tx) of arbitrary wallets on every collected launch -> attempts_<tag>.json {mint: {wallet6: [ok, slot_off]}}
import sys, os, json, gzip, glob, collections
from multiprocessing import Pool
D = "/home/moiz/sniper-data/collect"; RUNS = ["run_20261021_2207", "run_20261022_1543"]
W = {w: w[:6] for w in sys.argv[2].split(",")}; TAG = sys.argv[1]
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
                    if r[14] in W and r[15] == 1 and r[12] == 0: out[m].setdefault(W[r[14]], [1, r[2] - c["slot"]])
                elif r[6] in W and r[12] == 1: out[m].setdefault(W[r[6]], [0, r[2] - c["slot"]])
        except (EOFError, OSError): pass
    return dict(out)
if __name__ == "__main__":
    dirs = sorted(glob.glob(os.path.join(D, "phaseA", "b*"))) + sorted(glob.glob(os.path.join(D, os.environ.get("RP_PHASEA_R2", "phaseA_fwd"), "b*")))
    res = {}
    with Pool(14) as p:
        for o in p.imap_unordered(work, dirs):
            for m, v in o.items(): res.setdefault(m, {}).update(v)
    json.dump(res, open(os.environ.get("ATT_ANY_OUT", f"attempts_{TAG}.json"), "w"))
    print(TAG, "launches attempted:", len(res), dict(collections.Counter(w for v in res.values() for w in v)))
