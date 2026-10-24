#!/usr/bin/env python3
# READ-ONLY, offline: define FAST SNIPER wallets from the collector's trade rows (both runs, every launch):
#   a wallet is a fast sniper if it bought within 2 slots of the create on >= 5 different launches AND >= 50% of all its
#   (successful) buys in the collected data were within 2 slots of their launch's create.
# out: fast_snipers.json {"rule": ..., "wallets": {wallet: [n_fast_launches, n_buys, share_fast]}, "all": per-wallet counters for wallets with >=5 buys}
import sys, os, json, gzip, glob, zlib, collections
from multiprocessing import Pool
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core"); import rp
D = "/home/moiz/sniper-data/collect"; RUNS = {"R1": "phaseA", "R2": "phaseA_fwd"}
L = None
def init():
    global L
    L = {m: c["slot"] for m, c in rp.load_launches().items()}
def work(job):
    run, b = job; nb = collections.Counter(); nf = collections.Counter(); fl = collections.defaultdict(set); seen = set()
    for f in glob.glob(os.path.join(D, RUNS[run], f"b{b:03d}", "*.jsonl.gz")):
        try:
            for line in gzip.open(f, "rt"):
                if line[2] != "T": continue
                r = json.loads(line)
                if r[12] or r[15] != 1: continue                 # failed or sell
                k = (r[5], r[13])
                if k in seen: continue
                seen.add(k)
                S = L.get(r[1])
                if S is None: continue
                u = r[14]; nb[u] += 1
                if r[2] - S <= 2: nf[u] += 1; fl[u].add(r[1])
        except (EOFError, OSError, zlib.error): pass
    return nb, nf, {u: list(v) for u, v in fl.items()}
if __name__ == "__main__":
    NB = collections.Counter(); NF = collections.Counter(); FL = collections.defaultdict(set)
    jobs = [(run, b) for run in RUNS for b in range(256)]
    with Pool(8, initializer=init) as p:
        for i, (nb, nf, fl) in enumerate(p.imap_unordered(work, jobs)):
            NB.update(nb); NF.update(nf)
            for u, v in fl.items(): FL[u].update(v)
            if i % 64 == 0: print(i, "/", len(jobs), "wallets", len(NB), flush=True)
    fast = {u: [len(FL[u]), NB[u], round(NF[u] / NB[u], 3)] for u in NB if len(FL[u]) >= 5 and NF[u] / NB[u] >= 0.5}
    allw = {u: [len(FL[u]), NB[u], round(NF[u] / NB[u], 3)] for u in NB if NB[u] >= 5}
    json.dump(dict(rule="buy within 2 slots of create on >=5 launches and >=50% of its buys within 2 slots", wallets=fast, all=allw), open("fast_snipers.json", "w"))
    print("wallets with buys", len(NB), "| fast snipers", len(fast), "| their buys", sum(v[1] for v in fast.values()), "of", sum(NB.values()))
    for u, v in sorted(fast.items(), key=lambda kv: -kv[1][0])[:25]: print("  ", u, v)
