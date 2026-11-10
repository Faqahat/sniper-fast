#!/usr/bin/env python3
"""WHALEFLIP step 2 [MEASURED, read-only]: from the raw 24/7 recordings (every pump.fun tx), every successful tx on a mint where one of
our live pre-send windows FILLED (r39..r48, from w1's fills_rNN.pkl), restricted to recording files within +-150 s of a fill.
Row: s, i, sig, sg (first signer), cl (a CloseAccount ix in the tx), tb = [[mint, owner, pre, post], ...] for our mints, sd = signer lamport delta.
Also per file: max block index seen per slot (for the block-position clock, as c37lib).
Out: /home/it/sniper-data/filters3/whaleflip/raw/<recording>/<file>.jsonl  + .maxi.json
usage: w2_raw.py WORKERS"""
import sys, os, gzip, json, glob, pickle, re
from multiprocessing import Pool
D = "/home/it/sniper-data"
OUT = f"{D}/filters3/whaleflip/raw"
RECS = ["run_20261029_1400", "run_20261030_1355", "run_20261031_1350", "run_20261102_1250"]
MINTS = None
PRE = re.compile(rb'^\{"s":(\d+),"i":(\d+)')


def init(ms):
    global MINTS; MINTS = ms


def job(a):
    src, dst = a
    if os.path.exists(dst): return dst, -1
    n = 0; maxi = {}
    with gzip.open(src, "rb") as f, open(dst + ".tmp", "w") as o:
        try:
            for l in f:
                m = PRE.match(l)
                if m:
                    s = int(m.group(1)); i = int(m.group(2))
                    if i > maxi.get(s, -1): maxi[s] = i
                k = l.find(b'"mints":[')
                if k < 0: continue
                seg = l[k + 9:l.find(b"]", k)]
                if not any(x.strip(b'"') in MINTS for x in seg.split(b",") if x): continue
                d = json.loads(l)
                if d.get("err") is not None: continue
                sg = (d.get("signers") or [None])[0]
                tb = [x for x in (d.get("tb") or []) if x[0].encode() in MINTS]
                sd = dict((a_, v) for a_, v in (d.get("sd") or []))
                o.write(json.dumps({"s": d["s"], "i": d.get("i"), "sig": d.get("sig"), "sg": sg, "cl": "CloseAccount" in (d.get("ixn") or []),
                                    "tb": tb, "sd": sd.get(sg, 0)}, separators=(",", ":")) + "\n"); n += 1
        except EOFError:
            pass                                    # the live file still being written: keep what was read
    json.dump(maxi, open(dst + ".maxi.json", "w"))
    os.rename(dst + ".tmp", dst)
    return dst, n


if __name__ == "__main__":
    nw = int(sys.argv[1])
    ms = set(); times = []
    for fn in sorted(glob.glob(f"{D}/filters3/whaleflip/fills_r*.pkl")):
        for x in pickle.load(open(fn, "rb"))["fills"]:
            m = x["fills"][0].get("mint") or x.get("mint") or (x.get("trig") or {}).get("mint")
            ms.add(m.encode()); times.append(x["fills"][0]["t"] / 1e9)
    times.sort()
    import bisect
    jobs = []
    for rec in RECS:
        os.makedirs(f"{OUT}/{rec}", exist_ok=True)
        for fn in sorted(os.listdir(f"{D}/collect/{rec}/txs")):
            t0 = int(fn.split("_")[1].split(".")[0])
            k = bisect.bisect_left(times, t0 - 150)
            if k < len(times) and times[k] <= t0 + 300 + 150:
                jobs.append((f"{D}/collect/{rec}/txs/{fn}", f"{OUT}/{rec}/{fn[:-3]}"))
    print("mints", len(ms), "fills", len(times), "files", len(jobs), flush=True)
    tot = 0
    with Pool(nw, initializer=init, initargs=(ms,)) as p:
        for k, (d, n) in enumerate(p.imap_unordered(job, jobs)):
            tot += max(n, 0)
            if k % 50 == 0: print(k, len(jobs), tot, flush=True)
    print("done", len(jobs), tot, flush=True)
