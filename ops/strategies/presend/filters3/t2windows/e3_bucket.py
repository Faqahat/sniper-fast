#!/usr/bin/env python3
"""T2-WINDOWS step 3 [MEASURED, read-only on inputs]: e2's per-file raw rows -> 64 per-mint buckets (crc32(mint) % 64), so one bucket holds
the full chain history (within the recordings) of its mints; + the global block-index clock (slot -> max idx) and the dip bots' txs.
Out: /home/it/sniper-data/filters3/t2windows/bk/b<NN>.jsonl (row = [s, i, sig, sg, cl, [[mint, owner, pre, post], ...]]),
     maxi.pkl, bots.pkl"""
import os, json, glob, zlib, pickle
D = "/home/it/sniper-data/filters3/t2windows"
NB = 64

if __name__ == "__main__":
    os.makedirs(f"{D}/bk", exist_ok=True)
    outs = [open(f"{D}/bk/b{k:02d}.jsonl", "w") for k in range(NB)]
    maxi = {}; bots = []; n = 0
    fs = sorted([p for p in glob.glob(f"{D}/raw/*/txs_*.jsonl") if not p.endswith(".bots.jsonl")], key=lambda p: int(os.path.basename(p).split("_")[1].split(".")[0]))
    for fn in fs:
        for l in open(fn):
            d = json.loads(l)
            by = {}
            for x in d["tb"]:
                by.setdefault(zlib.crc32(x[0].encode()) % NB, []).append(x)
            for k, tb in by.items():
                outs[k].write(json.dumps([d["s"], d["i"], d["sig"], d["sg"], d["cl"], tb], separators=(",", ":")) + "\n")
            n += 1
        for s, i in json.load(open(fn + ".maxi.json")).items():
            s = int(s)
            if i > maxi.get(s, -1): maxi[s] = i
        if os.path.exists(fn + ".bots.jsonl"):
            for l in open(fn + ".bots.jsonl"):
                d = json.loads(l); bots.append((d["s"], d["i"], d["sg"], d["tb"]))
    for o in outs: o.close()
    pickle.dump(maxi, open(f"{D}/maxi.pkl", "wb"))
    bots = sorted(set((s, i, sg, json.dumps(tb)) for s, i, sg, tb in bots))
    pickle.dump([(s, i, sg, json.loads(tb)) for s, i, sg, tb in bots], open(f"{D}/bots.pkl", "wb"))
    print("rows", n, "slots", len(maxi), "bot txs", len(bots), "files", len(fs))
