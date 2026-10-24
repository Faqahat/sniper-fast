#!/usr/bin/env python3
# READ-ONLY, offline. One pass over the collector's raw txs of both runs:
#  C rows: every pump.fun CreateEvent (quote mint at +74 after the 4 pubkeys, all-zero = SOL; initial virtual quote
#          reserves at +16; mayhem flag at +72) -> the quote of EVERY launch (also launches without a dev buy)
#  T rows: every NON-SOL-quoted TradeEvent (virtual_sol_reserves == 0): quote mint at E+37, net quote amount at E+69,
#          virtual quote reserves E+77, real quote reserves E+85 (E = 262 + len(ix_name)); fees in quote units
#  W rows: per tx with a non-SOL trade: payer SOL delta, tips, fee, programs, token-balance deltas of wSOL / quote mints
#          (swap legs -> measured SOL<->quote rates and swap costs)
# usage: python3 -I ns_extract.py  (writes data/raw_<run>/<file>.jsonl.gz)
import os, sys, json, gzip, glob, base64, zlib, re
from multiprocessing import Pool
D = "/home/moiz/sniper-data/collect"; OUT = "/home/moiz/sniper/ops/overnight/nonsol/data"
RUNS = {"R1": "run_20261021_2207", "R2": "run_20261022_1543"}
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238]); CD = bytes.fromhex("1b72a94ddeeb6376")
WSOL = "So11111111111111111111111111111111111111112"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
RX = re.compile(r'"(vdt/007mYe[A-Za-z0-9+/=]*)"')
def dec(e):
    try: return base64.b64decode(e + "=" * (-len(e) % 4))
    except Exception: return None
def create_row(raw, r):
    o = 8
    for _ in range(3):
        ln = int.from_bytes(raw[o:o + 4], "little"); o += 4 + ln
        if ln > 400: return None
    if len(raw) < o + 128 + 106: return None
    mint = b58(raw[o:o + 32]); user = b58(raw[o + 64:o + 96]); creator = b58(raw[o + 96:o + 128]); p = o + 128
    u = lambda k: int.from_bytes(raw[p + k:p + k + 8], "little")
    qb = raw[p + 74:p + 106]
    quote = "SOL" if (len(qb) < 32 or qb == b"\0" * 32) else b58(qb)
    x114 = u(114) if len(raw) >= p + 122 else None
    return ["C", mint, int(r["s"]), int(r["i"]), r.get("bt"), r["sig"], quote, u(16), u(8), raw[p + 72], raw[p + 73], x114, raw[p + 122:].hex(), user, creator]
def work(args):
    run, path = args
    tag = os.path.basename(path).split(".")[0]
    od = os.path.join(OUT, "raw_" + run); outp = os.path.join(od, tag + ".jsonl.gz")
    if os.path.exists(outp): return 0
    rows = []
    try:
        for line in gzip.open(path, "rt"):
            hasc = "G3KpTd7rY3" in line
            hasq = False
            for mt in RX.finditer(line):
                if mt.group(1)[128:140] == "AAAAAAAAAAAA": hasq = True; break
            if not (hasc or hasq): continue
            try: r = json.loads(line)
            except Exception: continue
            if r.get("err"): continue
            j = 0; qms = set(); ntrade = 0
            for e in r.get("ev") or []:
                raw = dec(e)
                if raw is None: continue
                if raw[:8] == CD:
                    c = create_row(raw, r)
                    if c: rows.append(c)
                    continue
                if raw[:8] != TD or len(raw) < 262: continue
                u = lambda k: int.from_bytes(raw[k:k + 8], "little")
                if u(97) != 0: j += 1; continue
                ln = int.from_bytes(raw[258:262], "little")
                if ln > 64 or 262 + ln + 93 > len(raw): j += 1; continue
                E = 262 + ln
                qm = b58(raw[E + 37:E + 69]); qms.add(qm); ntrade += 1
                rows.append(["T", b58(raw[8:40]), int(r["s"]), int(r["i"]), r.get("bt"), r["sig"], j, b58(raw[57:89]), raw[56], u(48), u(105), u(121),
                             qm, u(E + 69), u(E + 77), u(E + 85), u(161), u(169), u(209), u(217), raw[262:E].decode("ascii", "replace"),
                             u(E + 17), u(E + 25)])
                j += 1
            if ntrade:
                payer = (r.get("signers") or [None])[0]
                sdp = next((d for a, d in (r.get("sd") or []) if a == payer), 0)
                tipsum = sum(x[1] for x in (r.get("tips") or []) if isinstance(x, (list, tuple)) and len(x) > 1)
                tb = [x for x in (r.get("tb") or []) if x[0] == WSOL or x[0] in qms]
                tb = [[x[0], x[1], x[2], x[3]] for x in tb if (x[3] or 0) != (x[2] or 0)]
                rows.append(["W", r["sig"], int(r["s"]), int(r["i"]), payer, sdp, tipsum, r.get("fee"), r.get("cu"), r.get("progs"), (r.get("ixn") or [])[:40], tb, len(r.get("signers") or [])])
    except (EOFError, OSError, zlib.error) as ex:
        rows.append(["ERR", str(ex)])
    tmp = outp + ".tmp"
    with gzip.open(tmp, "wt", compresslevel=3) as f:
        for x in rows: f.write(json.dumps(x, separators=(",", ":")) + "\n")
    os.rename(tmp, outp)
    return 1
if __name__ == "__main__":
    jobs = []
    for run, d in RUNS.items():
        os.makedirs(os.path.join(OUT, "raw_" + run), exist_ok=True)
        jobs += [(run, p) for p in sorted(glob.glob(os.path.join(D, d, "txs", "*.jsonl.gz")))]
    n = 0
    with Pool(6) as p:
        for k in p.imap_unordered(work, jobs):
            n += 1
            if n % 25 == 0: print("files", n, "/", len(jobs), flush=True)
    print("DONE", n, flush=True)
