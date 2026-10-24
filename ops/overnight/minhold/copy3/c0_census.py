#!/usr/bin/env python3
# census rows (one per wallet-mint) for the 3 study wallets, all runs -> out/census3.json ; also run time windows (PKT)
import gzip, glob, json, collections, time, os
W = ["Fsb6Ns75tgGRom5TJWK7ZA89XLPgCoyuhqeEdLgfbZfy", "pXGQ6J2ziRCvmYSLTT55FASf2jSHeCD6gju5xka31yV", "4vw54BmAogeRV3vPKWyFet5yf8DTLcREzdSzx4rw9Ud9"]
WS = set(W); rows = []
from multiprocessing import Pool
def scan(f):
    out = []
    for line in gzip.open(f, "rt"):
        if any(w in line[:60] for w in W):
            r = json.loads(line)
            if r[0] in WS: out.append(r)
    return out
if __name__ == "__main__":
    fs = sorted(glob.glob("/home/moiz/sniper/ops/overnight/census/parts/*.jsonl.gz"))
    with Pool(8) as p:
        for o in p.imap_unordered(scan, fs): rows += o
    json.dump(rows, open("out/census3.json", "w"))
    c = collections.Counter((r[0][:8], r[2]) for r in rows)
    for k in sorted(c): print(k, c[k])
    # run windows from launches
    for run in ("run_20261021_2207", "run_20261022_1543", "run_20261023_1426"):
        bts = [json.loads(l)["bt"] for l in open(f"/home/moiz/sniper-data/collect/{run}/launches.jsonl") if l.strip()]
        f = lambda t: time.strftime("%m-%d %H:%M", time.gmtime(t + 18000))
        print(run, "launches", len(bts), "PKT", f(min(bts)), "->", f(max(bts)), f"{(max(bts)-min(bts))/3600:.1f} h")
