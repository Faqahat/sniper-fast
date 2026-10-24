#!/usr/bin/env python3
# PASS 3 (read-only, offline): exact SOL deltas of candidate wallets from the RAW collected txs (field sd = per-account
# lamport change of each tx). Captures what the trade events miss: bot/router fees inside the tx, ATA rent, tips, failed
# txs, and post-graduation AMM sells of the same mints. Every tx in the collection touches >= 1 launch mint of the run.
# Output: one row per (candidate wallet, tx): [wallet, sig, slot, idx, bt, mints, delta, fee, tips, err, signer0, ixn]
# usage: python3 -I w3_sd.py <wallets.json (list)> <run dir> <out.jsonl.gz> [procs]
import sys, os, json, gzip, glob, re, zlib
from multiprocessing import Pool
WF, RUN, OUT = sys.argv[1], sys.argv[2], sys.argv[3]; PROCS = int(sys.argv[4]) if len(sys.argv) > 4 else 8
C = set(json.load(open(WF)))
ACC = re.compile(r'\["([1-9A-HJ-NP-Za-km-z]{32,44})",(-?\d+)\]')

def work(path):
    out = []
    try:
        with gzip.open(path, "rt") as fh:
            for line in fh:
                i = line.rfind('"sd":[')
                if i < 0: continue
                j = line.find('"tips":', i)
                seg = line[i:j if j > 0 else len(line)]
                hit = [a for a, _ in ACC.findall(seg) if a in C]
                if not hit:
                    continue
                try: r = json.loads(line)
                except Exception: continue
                sd = {a: v for a, v in (r.get("sd") or [])}
                for a in set(hit):
                    out.append([a, r["sig"], r["s"], r["i"], r.get("bt"), r.get("mints") or [], sd.get(a, 0), r.get("fee"), r.get("tips") or [],
                                1 if r.get("err") else 0, (r.get("signers") or [None])[0], (r.get("ixn") or [])[:8]])
    except (EOFError, OSError, zlib.error): pass
    return out

if __name__ == "__main__":
    files = sorted(glob.glob(os.path.join(RUN, "txs", "*.jsonl.gz")))
    n = 0
    with Pool(PROCS) as p, gzip.open(OUT, "wt", compresslevel=3) as f:
        for k, rows in enumerate(p.imap_unordered(work, files), 1):
            for r in rows: f.write(json.dumps(r, separators=(",", ":")) + "\n")
            n += len(rows)
            if k % 25 == 0: print(f"{k}/{len(files)} chunks, {n} rows", flush=True)
    print("DONE", n, flush=True)
