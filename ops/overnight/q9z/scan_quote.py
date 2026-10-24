#!/usr/bin/env python3
# READ-ONLY, offline: quote mint of every collected launch, decoded from the pump.fun V3 trade event of its create tx
# (quote_mint = 32 bytes after ix_name + 37; all-zero = SOL). -> quote_by_mint.json {mint: quote_mint or "SOL"}
import os, json, gzip, glob, zlib, base64
from multiprocessing import Pool
D = "/home/moiz/sniper-data/collect"; HERE = os.path.dirname(os.path.abspath(__file__))
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238])
CS = {}
for run in ("run_20261021_2207", "run_20261022_1543"):
    for l in open(os.path.join(D, run, "launches.jsonl")):
        try: c = json.loads(l)
        except Exception: continue
        CS[c["sig"]] = c["mint"]
def quote_of(ev_list, mint):
    for s in ev_list or []:
        try: raw = base64.b64decode(s + "=" * (-len(s) % 4))
        except Exception: continue
        if raw[:8] != TD or len(raw) < 262: continue
        if b58(raw[8:40]) != mint: continue
        n = int.from_bytes(raw[258:262], "little"); o = 262 + n
        q = raw[o + 37:o + 69]
        if len(q) < 32: return "old-event"
        return "SOL" if q == b"\0" * 32 else b58(q)
    return None
def work(f):
    out = {}
    try:
        for line in gzip.open(f, "rt"):
            i = line.find('"sig":"')
            if i < 0: continue
            sig = line[i + 7:line.find('"', i + 7)]
            m = CS.get(sig)
            if not m: continue
            r = json.loads(line); q = quote_of(r.get("ev"), m)
            if q: out[m] = q
    except (EOFError, OSError, zlib.error): pass
    return out
if __name__ == "__main__":
    files = sorted(glob.glob(os.path.join(D, "run_20261021_2207", "txs", "*.jsonl.gz"))) + sorted(glob.glob(os.path.join(D, "run_20261022_1543", "txs", "*.jsonl.gz")))
    Q = {}
    with Pool(8) as p:
        for o in p.imap_unordered(work, files): Q.update(o)
    json.dump(Q, open(os.path.join(HERE, "quote_by_mint.json"), "w"))
    import collections
    print("launch create sigs", len(CS), "quote decoded", len(Q)); print(collections.Counter(Q.values()).most_common(15))
