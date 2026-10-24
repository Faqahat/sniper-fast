#!/usr/bin/env python3
"""Independent extractor: raw collector tx chunks -> per-mint decoded pump.fun events.

Reads /home/moiz/sniper-data/collect/run_20261022_1543/txs/*.jsonl.gz directly
(not the pre-extracted phaseA rows, not anything in ops/overnight/core/).

Output: verify/work/chain_events.json.gz
  {mint: {"trades": [...], "creates": [...]}} for the mints listed in the result file,
  plus per-slot tx coverage counts (all txs, success+failed) to detect collector gaps.
Run:  python3 -I extract.py
"""
import base64
import binascii
import glob
import gzip
import json
import os
import struct
import sys
import zlib
from collections import Counter
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from b58 import b58enc, b58dec  # noqa: E402

RAW = "/home/moiz/sniper-data/collect/run_20261022_1543/txs"
RESULT = "/home/moiz/sniper/ops/overnight/report/s4_forward.json"
OUT = os.path.join(HERE, "work", "chain_events.json.gz")

TE = bytes([189, 219, 127, 211, 78, 230, 97, 238])  # TradeEvent
CE = bytes([27, 114, 169, 77, 222, 235, 99, 118])   # CreateEvent

TARGET = None  # set of 32-byte mint keys (filled in worker init)


def _init(targets):
    global TARGET
    TARGET = targets


def _rstr(b, o):
    n = struct.unpack_from("<I", b, o)[0]
    return b[o + 4:o + 4 + n].decode("utf8", "replace"), o + 4 + n


def dec_trade(b):
    d = {}
    d["mint"] = b58enc(b[8:40])
    d["sol"], d["tok"] = struct.unpack_from("<QQ", b, 40)
    d["is_buy"] = b[56]
    d["user"] = b58enc(b[57:89])
    d["ts"], d["vsol"], d["vtok"], d["rsol"], d["rtok"] = struct.unpack_from("<qQQQQ", b, 89)
    d["fee_recipient"] = b58enc(b[129:161])
    d["fee_bps"], d["fee"] = struct.unpack_from("<QQ", b, 161)
    d["creator"] = b58enc(b[177:209])
    d["cfee_bps"], d["cfee"] = struct.unpack_from("<QQ", b, 209)
    d["evlen"] = len(b)
    # ix_name string lives after track_volume(1)+3*u64+i64 = offset 258 (only when long enough)
    try:
        if len(b) >= 262:
            nm, _ = _rstr(b, 258)
            d["ixname"] = nm if len(nm) < 40 else None
    except Exception:
        d["ixname"] = None
    return d


def dec_create(b):
    d = {}
    o = 8
    d["name"], o = _rstr(b, o)
    d["symbol"], o = _rstr(b, o)
    d["uri"], o = _rstr(b, o)
    d["mint"] = b58enc(b[o:o + 32]); o += 32
    d["bonding_curve"] = b58enc(b[o:o + 32]); o += 32
    d["user"] = b58enc(b[o:o + 32]); o += 32
    d["creator"] = b58enc(b[o:o + 32]); o += 32
    d["ts"], d["vtok0"], d["vsol0"], d["rtok0"], d["supply"] = struct.unpack_from("<qQQQQ", b, o); o += 40
    rest = b[o:]
    d["token_program"] = b58enc(rest[:32]) if len(rest) >= 32 else None
    d["tail_hex"] = rest[32:].hex()
    d["is_mayhem_byte"] = rest[32] if len(rest) > 32 else None
    return d


def work(path):
    trades, creates = [], []
    slotcnt = Counter()
    nlines = 0
    bad_json = 0
    truncated = False
    try:
        with gzip.open(path, "rt") as fh:
            for ln in fh:
                try:
                    o = json.loads(ln)
                except Exception:
                    bad_json += 1
                    continue
                nlines += 1
                s = o.get("s")
                slotcnt[s] += 1
                evs = o.get("ev") or []
                hits = []
                for k, e in enumerate(evs):
                    if len(e) < 56:
                        continue
                    try:
                        head = binascii.a2b_base64(e[:56])
                    except binascii.Error:
                        continue
                    disc = head[:8]
                    if disc != TE and disc != CE:
                        continue
                    if disc == TE:
                        if head[8:40] not in TARGET:
                            continue
                    try:
                        b = base64.b64decode(e, validate=True)
                    except binascii.Error:
                        continue
                    if disc == TE:
                        if len(b) < 225:
                            continue
                        d = dec_trade(b)
                        d["kind"] = "trade"
                    else:
                        try:
                            d = dec_create(b)
                        except Exception:
                            continue
                        if b58dec(d["mint"]) not in TARGET:
                            continue
                        d["kind"] = "create"
                    d["k"] = k
                    d["raw_b64"] = e if disc == CE else None
                    hits.append(d)
                if not hits:
                    continue
                base = {
                    "s": s, "i": o.get("i"), "bt": o.get("bt"), "sig": o.get("sig"),
                    "err": o.get("err"), "fee": o.get("fee"), "signers": o.get("signers"),
                    "ixn": o.get("ixn"), "progs": o.get("progs"), "tips": o.get("tips"),
                    "nev": len(evs), "file": os.path.basename(path),
                }
                for d in hits:
                    d.update(base)
                    (trades if d["kind"] == "trade" else creates).append(d)
    except (EOFError, zlib.error, OSError) as ex:  # truncated last chunk(s)
        truncated = repr(ex)
    return path, trades, creates, dict(slotcnt), nlines, bad_json, truncated


def main():
    res = json.load(open(RESULT))
    mints = sorted({x["mint"] for x in res})
    targets = {b58dec(m) for m in mints}
    assert all(len(t) == 32 for t in targets), "bad mint decode"
    files = sorted(glob.glob(os.path.join(RAW, "*.jsonl.gz")))
    print("files", len(files), "target mints", len(mints), flush=True)
    per = {m: {"trades": [], "creates": []} for m in mints}
    slotcov = Counter()
    meta = []
    with Pool(14, initializer=_init, initargs=(targets,)) as pool:
        for path, trades, creates, sc, nl, bj, tr in pool.imap_unordered(work, files):
            for d in trades:
                per[d["mint"]]["trades"].append(d)
            for d in creates:
                per[d["mint"]]["creates"].append(d)
            for s, c in sc.items():
                slotcov[s] += c
            meta.append({"file": os.path.basename(path), "lines": nl, "bad_json": bj, "truncated": tr})
            if tr or bj:
                print("  note", os.path.basename(path), "lines", nl, "bad_json", bj, "trunc", tr, flush=True)
    for m in per:
        per[m]["trades"].sort(key=lambda d: (d["s"], d["i"], d["k"]))
        per[m]["creates"].sort(key=lambda d: (d["s"], d["i"], d["k"]))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with gzip.open(OUT, "wt") as fh:
        json.dump({"per_mint": per, "slot_cov": {str(k): v for k, v in sorted(slotcov.items()) if k is not None},
                   "files": sorted(meta, key=lambda x: x["file"])}, fh)
    nt = sum(len(v["trades"]) for v in per.values())
    nc = sum(len(v["creates"]) for v in per.values())
    print("done: trades", nt, "creates", nc, "lines", sum(x["lines"] for x in meta), flush=True)


if __name__ == "__main__":
    main()
