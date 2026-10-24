#!/usr/bin/env python3
"""Extract EVERY tx (success or failed) that touches one of the 269 mints in slots cs..cs+10
(block-order anchors for the engine's arrival timeline). Output: work/alltx_early.json.gz"""
import glob
import gzip
import json
import os
import sys
import zlib
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = "/home/moiz/sniper-data/collect/run_20261022_1543/txs"
RESULT = "/home/moiz/sniper/ops/overnight/report/s4_forward.json"
LAUNCHES = "/home/moiz/sniper-data/collect/run_20261022_1543/launches.jsonl"
SPAN = 10
CS = None


def _init(cs):
    global CS
    CS = cs


def work(path):
    out = []
    try:
        with gzip.open(path, "rt") as fh:
            for ln in fh:
                try:
                    o = json.loads(ln)
                except Exception:
                    continue
                ms = o.get("mints") or []
                for m in ms:
                    c = CS.get(m)
                    if c is not None and c <= o["s"] <= c + SPAN:
                        out.append({"mint": m, "s": o["s"], "i": o["i"], "sig": o["sig"], "err": o["err"] is not None,
                                    "errv": str(o["err"])[:80] if o["err"] is not None else None,
                                    "signers": o.get("signers"), "ixn": (o.get("ixn") or [])[:8], "nev": len(o.get("ev") or []),
                                    "fee": o.get("fee"), "tips": o.get("tips")})
    except (EOFError, zlib.error, OSError):
        pass
    return out


def main():
    mints = {x["mint"] for x in json.load(open(RESULT))}
    cs = {}
    for ln in open(LAUNCHES):
        try:
            o = json.loads(ln)
        except Exception:
            continue
        if o.get("mint") in mints:
            cs[o["mint"]] = o["slot"]
    files = sorted(glob.glob(os.path.join(RAW, "*.jsonl.gz")))
    allx = []
    with Pool(14, initializer=_init, initargs=(cs,)) as pool:
        for part in pool.imap_unordered(work, files):
            allx.extend(part)
    seen = set()
    ded = []
    for x in sorted(allx, key=lambda d: (d["mint"], d["s"], d["i"])):
        k = (x["mint"], x["sig"])
        if k in seen:
            continue
        seen.add(k)
        ded.append(x)
    with gzip.open(os.path.join(HERE, "work", "alltx_early.json.gz"), "wt") as fh:
        json.dump(ded, fh)
    print("txs", len(ded), "failed", sum(1 for x in ded if x["err"]))


if __name__ == "__main__":
    main()
