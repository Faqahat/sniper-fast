#!/usr/bin/env python3
"""SELECT s0 (read-only): CreateEvents (mint, creator, slot, bt, mayhem, quote, name, symbol) from run_20261027_1410 chunks
(the dv8 creates.json ends 10-28 01:12 PKT); with arg "all": every run_2026102* chunk incl. name/symbol/uri -> creates_all.json. Out: sniper-data/e2x1_dissect/select/creates_new.json"""
import sys, gzip, json, glob, os
from multiprocessing import Pool
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real")
import decode as DC
OUT = "/home/moiz/sniper-data/e2x1_dissect/select"
def one(fn):
    out = []
    try:
        with gzip.open(fn, "rt") as f:
            for line in f:
                if '"Create' not in line: continue
                r = json.loads(line)
                if r.get("err") is not None: continue
                ixn = r.get("ixn") or []
                if not any(x in ("Create", "CreateV2") for x in ixn): continue
                for b in DC.chunks_of(r.get("ev")):
                    if b[:8] == DC.CREATE_EV:
                        rd = DC.Rd(b, 8)
                        try: nm, sy, uri = rd.st(), rd.st(), rd.st()
                        except Exception: nm = sy = uri = ""
                        c = DC.parse_create(b)
                        c.update(slot=r["s"], idx=r["i"], bt=r["bt"], name=nm[:40], symbol=sy[:20], uri=uri[:120])
                        out.append(c)
    except EOFError: pass
    return out
if __name__ == "__main__":
    ALL = len(sys.argv) > 1 and sys.argv[1] == "all"
    fs = sorted(glob.glob("/home/moiz/sniper-data/collect/run_2026102*/txs/*.jsonl.gz"))
    if not ALL: fs = [f for f in fs if "run_20261027_1410" in f and int(os.path.basename(f)[4:14]) >= 1793131000]
    with Pool(10) as p: res = p.map(one, fs, chunksize=1)
    C = {}
    for r in res:
        for c in r: C[c["mint"]] = c
    json.dump(C, open(f"{OUT}/creates_all.json" if ALL else f"{OUT}/creates_new.json", "w"))
    print(len(fs), "files", len(C), "creates")
