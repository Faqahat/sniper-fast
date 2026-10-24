#!/usr/bin/env python3
# READ-ONLY: non-SOL-quoted pump.fun curves (PUMP / USDC / USD1 ...). TradeEvent v2 (391 B) carries the quote mint at
# offset 303, the gross quote amount at 335, the virtual quote reserves at 343 and the real quote reserves at 351
# (verified on chain against the vault's balance change). One row per trade, bucketed by mint like phase A.
import sys, os, json, gzip, base64, binascii, zlib, glob
from multiprocessing import Pool
RUN, OUT = sys.argv[1], sys.argv[2]
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238])
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
def work(path):
    tag = os.path.basename(path).split(".")[0]; outs = {}
    def w(b, row):
        f = outs.get(b)
        if f is None: f = outs[b] = gzip.open(os.path.join(OUT, f"b{b:03d}", f"{tag}.jsonl.gz"), "wt", compresslevel=1)
        f.write(json.dumps(row, separators=(",", ":")) + "\n")
    try:
        for line in gzip.open(path, "rt"):
            if '"ev"' not in line: continue
            try: r = json.loads(line)
            except Exception: continue
            if r.get("err"): continue
            j = 0
            for e in r.get("ev") or []:
                try: raw = base64.b64decode(e + "=" * (-len(e) % 4))
                except (binascii.Error, ValueError): continue
                if raw[:8] != TD or len(raw) < 359: continue
                u = lambda o: int.from_bytes(raw[o:o + 8], "little")
                if u(97) != 0: j += 1; continue          # SOL-quoted: already in phase A
                m = b58(raw[8:40])
                ln = int.from_bytes(raw[258:262], "little")         # ix_name string (u32 length + bytes) shifts what follows
                if ln > 64 or 262 + ln + 93 > len(raw): j += 1; continue
                E = 262 + ln
                w(zlib.crc32(m.encode()) % 256, [m, r["s"], r["i"], r.get("bt"), r["sig"], j, b58(raw[57:89]), raw[56], u(48), u(105), b58(raw[E + 37:E + 69]), u(E + 69), u(E + 77), u(E + 85), u(161), u(209), raw[262:E].decode("ascii", "replace")])
                j += 1
    except (EOFError, OSError, zlib.error): pass
    for f in outs.values(): f.close()
    return 1
if __name__ == "__main__":
    for b in range(256): os.makedirs(os.path.join(OUT, f"b{b:03d}"), exist_ok=True)
    files = sorted(glob.glob(os.path.join(RUN, "txs", "*.jsonl.gz")))
    with Pool(14) as p: n = sum(p.imap_unordered(work, files))
    print("DONE", n, "chunks")
