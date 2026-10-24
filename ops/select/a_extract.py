#!/usr/bin/env python3
# PHASE A (read-only, offline): every txs/*.jsonl.gz chunk of a collect.py run -> compact per-event rows, bucketed by mint
# (256 buckets) so phase B can load one bucket at a time. One row per pump.fun TradeEvent (in log order inside the tx),
# plus one marker row per tx that touches a window mint without a trade event (transfers, burns, migration, AMM...).
# usage: python3 a_extract.py <run dir> <out dir> [procs]
import sys, os, json, gzip, base64, zlib, glob
from multiprocessing import Pool
RUN, OUT = sys.argv[1], sys.argv[2]; PROCS = int(sys.argv[3]) if len(sys.argv) > 3 else 14
TRADE = bytes([189, 219, 127, 211, 78, 230, 97, 238])
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
NB = 256
def bucket(m): return zlib.crc32(m.encode()) % NB
def work(path):
    tag = os.path.basename(path).split(".")[0]
    outs = {}
    def w(b, row):
        f = outs.get(b)
        if f is None: f = outs[b] = gzip.open(os.path.join(OUT, f"b{b:03d}", f"{tag}.jsonl.gz"), "wt", compresslevel=1)
        f.write(json.dumps(row, separators=(",", ":")) + "\n")
    n = 0
    def lines():                                   # chunks cut by a restart are truncated: keep everything before the cut
        try:
            for line in gzip.open(path, "rt"): yield line
        except (EOFError, OSError, zlib.error): pass
    for line in lines():
        try: r = json.loads(line)
        except Exception: continue
        tips = sum(d for _, d in r.get("tips") or [])
        base = [r["s"], r["i"], r.get("bt"), r["sig"], (r.get("signers") or [None])[0], r.get("fee"), r.get("cup"), r.get("cul"), r.get("cu"), tips, 1 if r.get("err") else 0]
        found = set(); j = 0
        for e in r.get("ev") or []:
            try: raw = base64.b64decode(e + "=" * (-len(e) % 4))
            except Exception: continue
            if raw[:8] != TRADE or len(raw) < 225: continue
            u = lambda o: int.from_bytes(raw[o:o + 8], "little")
            m = b58(raw[8:40]); found.add(m)
            w(bucket(m), ["T", m] + base + [j, b58(raw[57:89]), raw[56], u(40), u(48), u(97), u(105), u(169), u(217), u(161), u(209)]); j += 1
        for m in r.get("mints") or []:
            if m in found: continue
            tb = [x for x in r.get("tb") or [] if x[0] == m]
            w(bucket(m), ["X", m] + base + [r.get("ixn") or [], tb, (r.get("progs") or [])[:12]])
        n += 1
    for f in outs.values(): f.close()
    return n
if __name__ == "__main__":
    for b in range(NB): os.makedirs(os.path.join(OUT, f"b{b:03d}"), exist_ok=True)
    files = sorted(glob.glob(os.path.join(RUN, "txs", "*.jsonl.gz")))
    tot = 0
    with Pool(PROCS) as p:
        for k, n in enumerate(p.imap_unordered(work, files), 1):
            tot += n
            if k % 20 == 0: print(f"{k}/{len(files)} chunks, {tot} txs", flush=True)
    print("DONE", tot, flush=True)
