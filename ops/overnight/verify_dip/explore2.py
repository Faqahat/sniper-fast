#!/usr/bin/env python3
# decode CreateEvent / TradeEvent tails on one raw chunk and correlate with mayhem (InitializeMayhemState) creates
import gzip, json, base64, struct, sys, collections
TE = bytes([189, 219, 127, 211, 78, 230, 97, 238]); CE = bytes([27, 114, 169, 77, 222, 235, 99, 118])
A = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58e(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(A[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
def b64(s): return base64.b64decode(s + "=" * (-len(s) % 4))
f = sys.argv[1]; C = {}; cnt = collections.Counter(); tk = collections.Counter(); ex = {}
for line in gzip.open(f, "rt"):
    o = json.loads(line)
    ixn = o.get("ixn") or []
    for e in o.get("ev") or []:
        try: raw = b64(e)
        except Exception: continue
        if raw[:8] == CE:
            o2 = 8
            for _ in range(3):
                ln = struct.unpack_from("<I", raw, o2)[0]; o2 += 4 + ln
            mint = b58e(raw[o2:o2 + 32]); o2 += 128
            ts, vtok0, vsol0, rtok0, sup = struct.unpack_from("<qQQQQ", raw, o2); o2 += 40
            tp = b58e(raw[o2:o2 + 32]); o2 += 32; rest = raw[o2:]
            may_ix = "InitializeMayhemState" in ixn
            b0, b1 = rest[0], rest[1]; q = b58e(rest[2:34]); v = struct.unpack_from("<Q", rest, 34)[0]; w = struct.unpack_from("<Q", rest, 42)[0]
            tail = rest[50:].hex()
            C[mint] = (may_ix, b0, b1, q, v, w, vsol0)
            cnt[(may_ix, b0, b1, q[:6], vsol0 == 30_000_000_000)] += 1
            if (may_ix, b0, q[:6]) not in ex: ex[(may_ix, b0, q[:6])] = (mint, b0, b1, q, v, w, tail, vsol0, ixn[:6])
for k, v in cnt.most_common(): print(k, v)
for k, v in ex.items(): print("EX", k, v)
# trade events: decode tail after ix_name for mints created in this chunk
for line in gzip.open(f, "rt"):
    o = json.loads(line)
    if o.get("err"): continue
    for e in o.get("ev") or []:
        try: raw = b64(e)
        except Exception: continue
        if raw[:8] != TE: continue
        mint = b58e(raw[8:40])
        if mint not in C: continue
        nlen = struct.unpack_from("<I", raw, 258)[0]; name = raw[262:262 + nlen].decode(); rest = raw[262 + nlen:]
        b0 = rest[0]; q = b58e(rest[1:33]); x = rest[33:].hex()
        vsol = struct.unpack_from("<Q", raw, 97)[0]
        tk[(C[mint][0], C[mint][1], b0, q[:6], vsol < 200e9)] += 1
        if (C[mint][0], b0, q[:6]) not in ex: ex[(C[mint][0], b0, q[:6])] = 1; print("TEX", C[mint], name, b0, q, x[:120], vsol)
for k, v in tk.most_common(): print("TE", k, v)
