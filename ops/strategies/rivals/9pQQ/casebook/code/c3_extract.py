#!/usr/bin/env python3
"""CASEBOOK step 3: full raw tape (landed + failed) for picked tokens, one pass over only the needed files.
usage: c3_extract.py BATCH [BATCH...]   (reads casebook/pick_<batch>.tsv)
out  : casebook/tapes/<run>/<mint>.raw.jsonl.gz  (raw lines, chain order)
Read-only on the recordings; 3 workers (zcat|grep -F)."""
import sys, os, json, gzip, subprocess, collections
from multiprocessing import Pool
OUT = "/home/it/sniper-data/rivals/9pQQ/casebook"; COL = "/data/tapes/collect"
def job(a):
    fn, mints = a
    pf = f"/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/f3_9pqqcase/pat_{os.getpid()}.txt"
    open(pf, "w").write("\n".join(mints) + "\n")
    p = subprocess.run(f"zcat {fn} 2>/dev/null | grep -F -f {pf}", shell=True, capture_output=True)
    res = collections.defaultdict(list)
    for l in p.stdout.decode(errors="replace").splitlines():
        try: d = json.loads(l)
        except Exception: continue
        ms = set(d.get("mints") or [])
        for m in mints:
            if m in ms or m in l: res[m].append(l)
    return fn, dict(res)
if __name__ == "__main__":
    picks = []
    for b in sys.argv[1:]:
        for l in open(f"{OUT}/pick_{b}.tsv"): picks.append(l.split("\t")[:2])
    by_run = collections.defaultdict(list)
    for run, m in picks: by_run[run].append(m)
    jobs = []
    for run, ms in by_run.items():
        os.makedirs(f"{OUT}/tapes/{run}", exist_ok=True)
        L = {}
        for l in open(f"{COL}/{run}/launches.jsonl"):
            d = json.loads(l)
            if d["mint"] in ms: L[d["mint"]] = d["bt"]
        last = {}
        for l in open(f"{OUT}/trips_{run}.jsonl"):
            t = json.loads(l)
            if t["mint"] in ms: last[t["mint"]] = max(last.get(t["mint"], 0), t["sbt"])
        files = sorted(os.listdir(f"{COL}/{run}/txs"))
        need = collections.defaultdict(list)
        for f in files:
            t0 = int(f.split("_")[1].split(".")[0])
            for m in ms:
                if m in L and L[m] - 400 <= t0 <= last.get(m, L[m]) + 1200: need[f"{COL}/{run}/txs/{f}"].append(m)
        jobs += [(f, mm) for f, mm in need.items()]
    print("files", len(jobs), flush=True)
    acc = collections.defaultdict(list)
    with Pool(3) as p:
        for k, (fn, res) in enumerate(p.imap_unordered(job, jobs)):
            run = fn.split("/")[-3]
            for m, ls in res.items(): acc[(run, m)] += ls
            if k % 20 == 0: print(k, len(jobs), flush=True)
    for (run, m), ls in acc.items():
        rows = [(json.loads(l), l) for l in ls]
        rows.sort(key=lambda x: (x[0]["s"], x[0].get("i") or 0))
        seen = set()
        with gzip.open(f"{OUT}/tapes/{run}/{m}.raw.jsonl.gz", "wt") as fo:
            for d, l in rows:
                if d["sig"] in seen: continue
                seen.add(d["sig"]); fo.write(l + "\n")
    print("done", len(acc), flush=True)
