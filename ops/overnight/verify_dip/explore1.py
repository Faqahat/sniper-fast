#!/usr/bin/env python3
# quick look at one raw chunk: line count, parse speed, event layouts (TradeEvent tail, CreateEvent tail)
import gzip, json, base64, struct, time, sys, collections
TE = bytes([189, 219, 127, 211, 78, 230, 97, 238]); CE = bytes([27, 114, 169, 77, 222, 235, 99, 118])
A = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58e(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(A[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
def b64(s): return base64.b64decode(s + "=" * (-len(s) % 4))
f = sys.argv[1]; t0 = time.time(); n = 0; nerr = 0; lens = collections.Counter(); ixs = collections.Counter(); ctails = collections.Counter()
cvals = collections.Counter(); te_err = 0; evkinds = collections.Counter(); tails = collections.Counter(); samples = []
for line in gzip.open(f, "rt"):
    n += 1
    o = json.loads(line)
    if o.get("err"): nerr += 1
    for e in o.get("ev") or []:
        try: raw = b64(e)
        except Exception: evkinds['bad64'] += 1; continue
        evkinds[raw[:8].hex()] += 1
        if raw[:8] == TE:
            lens[len(raw)] += 1
            if o.get("err"): te_err += 1
            if len(raw) > 262:
                nlen = struct.unpack_from("<I", raw, 258)[0]
                name = raw[262:262 + nlen].decode("utf8", "replace"); ixs[name] += 1
                tails[(len(raw) - 262 - nlen, raw[262 + nlen:].hex()[:40])] += 1
        elif raw[:8] == CE:
            o2 = 8; ss = []
            for _ in range(3):
                ln = struct.unpack_from("<I", raw, o2)[0]; ss.append(raw[o2 + 4:o2 + 4 + ln]); o2 += 4 + ln
            o2 += 128
            ts, vtok0, vsol0, rtok0, sup = struct.unpack_from("<qQQQQ", raw, o2); o2 += 40
            rest = raw[o2:]
            cvals[(vtok0, vsol0, rtok0, sup)] += 1
            ctails[(len(rest), b58e(rest[:32]) if len(rest) >= 32 else None, rest[32:].hex())] += 1
    if n >= 200000: break
dt = time.time() - t0
print("lines", n, "secs", round(dt, 1), "per line us", round(dt / n * 1e6, 1), "err lines", nerr, "TE in err txs", te_err)
print("event kinds", evkinds.most_common(8))
print("TE lengths", lens.most_common(10))
print("ix names", ixs.most_common(10))
print("TE tails after ix_name", tails.most_common(10))
print("create (vtok0,vsol0,rtok0,supply)", cvals.most_common(6))
print("create tails", ctails.most_common(8))
