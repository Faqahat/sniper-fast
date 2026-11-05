#!/usr/bin/env python3
"""T2-WINDOWS step 2 [MEASURED, read-only]: from the raw 24/7 recordings, every successful pump.fun tx on a CANDIDATE mint of runs
r39..r49 (e1 rec_<run>.pkl: every re-arm candidate (armed / skipped / deferred), every live T2 trigger (armed / skipped), every wide-shadow
trigger >= 3.9 %), in recording files inside [run's first record - 15 min, last record + 3 min]. Row = whaleflip/w2_raw.py's
(s, i, sig, sg, cl, tb (candidate mints only), sd) + per file the max block index per slot (block-position clock). Also every tx signed by a
known dip bot (any mint): bots/<file>.jsonl rows (s, i, sg, tb of its own accounts).
Out: /home/moiz/sniper-data/filters3/t2windows/raw/<recording>/<file>.jsonl + .maxi.json + .bots.jsonl
usage: e2_raw.py WORKERS"""
import sys, os, gzip, json, glob, pickle, re, bisect
from multiprocessing import Pool
D = "/home/moiz/sniper-data"
OUT = f"{D}/filters3/t2windows/raw"
RECS = ["run_20261029_1400", "run_20261030_1355", "run_20261031_1350", "run_20261102_1250", "run_20261103_1245"]
RUNS = [39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49]
BOTS = {"haqq6qnVBCZt97amh9VUFZRFCkD6NJxoYifacCuqqqq", "8PgC4ngpx6zUG3KFQAQHqSeePDFA7kGyEaA2yMoZ4HUk", "9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN",
        "8yYMhuYo1LzgCmeeg3vRkhRtJ8xFC7v7S4ufABtQXjS3", "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq", "2VggYpPumR3sV4K9vBqDzsmKzpB3BgSM4woRwbqqzweg"}
MINTS = None
PRE = re.compile(rb'^\{"s":(\d+),"i":(\d+)')
BOTB = [b.encode() for b in BOTS]


def init(ms):
    global MINTS; MINTS = ms


def job(a):
    src, dst = a
    if os.path.exists(dst): return dst, -1
    n = 0; maxi = {}
    with gzip.open(src, "rb") as f, open(dst + ".tmp", "w") as o, open(dst + ".bots.tmp", "w") as ob:
        try:
            for l in f:
                m = PRE.match(l)
                if m:
                    s = int(m.group(1)); i = int(m.group(2))
                    if i > maxi.get(s, -1): maxi[s] = i
                k = l.find(b'"mints":[')
                if k < 0: continue
                seg = l[k + 9:l.find(b"]", k)]
                hit = any(x.strip(b'"') in MINTS for x in seg.split(b",") if x)
                ks = l.find(b'"signers":[')
                bot = ks >= 0 and any(b in l[ks:ks + 200] for b in BOTB)
                if not hit and not bot: continue
                d = json.loads(l)
                if d.get("err") is not None: continue
                sg = (d.get("signers") or [None])[0]
                if bot and sg in BOTS:
                    ob.write(json.dumps({"s": d["s"], "i": d.get("i"), "sg": sg, "tb": [x for x in (d.get("tb") or []) if x[1] == sg]}, separators=(",", ":")) + "\n")
                if not hit: continue
                tb = [x for x in (d.get("tb") or []) if x[0].encode() in MINTS]
                sd = dict((a_, v) for a_, v in (d.get("sd") or []))
                o.write(json.dumps({"s": d["s"], "i": d.get("i"), "sig": d.get("sig"), "sg": sg, "cl": "CloseAccount" in (d.get("ixn") or []),
                                    "tb": tb, "sd": sd.get(sg, 0)}, separators=(",", ":")) + "\n"); n += 1
        except EOFError:
            pass                                    # a live file still being written: keep what was read
    json.dump(maxi, open(dst + ".maxi.json", "w"))
    os.rename(dst + ".bots.tmp", dst + ".bots.jsonl")
    os.rename(dst + ".tmp", dst)
    return dst, n


def cands():
    ms = set(); spans = []
    for r in RUNS:
        R = pickle.load(open(f"{D}/filters3/t2windows/rec_{r}.pkl", "rb"))
        spans.append((R["t_first"] / 1e9 - 900, R["t_last"] / 1e9 + 180))
        for w in R["wins"]: ms.add(w["mint"])
        for s in R["skips"]:
            if s.get("mint"): ms.add(s["mint"])
        for s in R["defers"]: ms.add(s["mint"])
        for w in R["wide"]:
            if (w.get("pct") or 0) >= 3.9: ms.add(w["mint"])
    return {m.encode() for m in ms if m}, spans


if __name__ == "__main__":
    nw = int(sys.argv[1])
    ms, spans = cands()
    jobs = []
    for rec in RECS:
        os.makedirs(f"{OUT}/{rec}", exist_ok=True)
        fs = sorted(os.listdir(f"{D}/collect/{rec}/txs"))
        for fn in fs:
            t0 = int(fn.split("_")[1].split(".")[0])
            if any(lo - 330 <= t0 <= hi for lo, hi in spans):
                jobs.append((f"{D}/collect/{rec}/txs/{fn}", f"{OUT}/{rec}/{fn[:-3]}"))
    print("mints", len(ms), "files", len(jobs), flush=True)
    tot = 0
    with Pool(nw, initializer=init, initargs=(ms,)) as p:
        for k, (d, n) in enumerate(p.imap_unordered(job, jobs)):
            tot += max(n, 0)
            if k % 25 == 0: print(k, len(jobs), tot, flush=True)
    print("done", len(jobs), tot, flush=True)
