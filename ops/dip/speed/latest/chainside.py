#!/usr/bin/env python3
# Chain side of every fire (raw recordings R3/R4 contain every pump tx, failed ones too): our buy tx (tips/accounts, CU price/limit, slot/index),
# the dump, the rivals that landed between the dump and us (tips, CU price, nonce-like 1st ix, failed pre-sends by the same signer on the
# same token in the 5 slots before the dump). Then: what explains our fire->seen delay?
import json, glob, gzip, collections, statistics, os
from multiprocessing import Pool
T = json.load(open("latest/timeline.json"))
RUNS = {"R3": "/home/moiz/sniper-data/collect/run_20261023_1426/txs", "R4": "/home/moiz/sniper-data/collect/run_20261024_1425/txs"}
files = []
for d in RUNS.values():
    for f in sorted(glob.glob(d + "/*.jsonl.gz")): files.append((int(os.path.basename(f)[4:14]), f))
files.sort()
MINTS = {r["mint"] for r in T}
want_slots = collections.defaultdict(set)
for r in T: want_slots[r["mint"]].update(range(r["dump_slot"] - 6, r["dump_slot"] + 4))
def pick_files(t0_ns):
    t = t0_ns / 1e9; out = [f for ts, f in files if ts - 40 <= t <= ts + 340]
    return out
need = collections.defaultdict(set)
for r in T:
    for f in pick_files(r["t0"]): need[f].add(r["mint"])
def scan(f):
    ms_ = need[f]; out = []
    try:
        for line in gzip.open(f, "rt"):
            if not any(m in line for m in ms_): continue
            try: x = json.loads(line)
            except Exception: continue
            for m in (x.get("mints") or []):
                if m in ms_ and int(x["s"]) in want_slots[m]:
                    out.append(dict(m=m, s=int(x["s"]), i=int(x["i"]), sig=x["sig"], err=str(x.get("err")), signer=(x.get("signers") or [None])[0], cup=x.get("cup"), cul=x.get("cul"),
                                    tips=x.get("tips"), ixn=(x.get("ixn") or [])[:6], progs=len(x.get("progs") or [])))
    except (EOFError, OSError): pass
    return out
if __name__ == "__main__":
    rows = []
    with Pool(10) as p:
        for o in p.imap_unordered(scan, sorted(need)): rows += o
    by = collections.defaultdict(dict)
    for x in rows: by[x["m"]][x["sig"]] = x
    json.dump({m: list(v.values()) for m, v in by.items()}, open("latest/chain_rows.json", "w"))
    print("fires", len(T), "| tokens with chain rows", len(by), "| rows", len(rows))
