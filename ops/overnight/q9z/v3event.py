#!/usr/bin/env python3
# READ-ONLY helper: decode pump.fun V3 TradeEvent incl. the quote leg (quote mint + quote amount + fees in quote units).
import base64
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238])
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
def decode(s):
    s = s.strip(); s += "=" * (-len(s) % 4)
    try: raw = base64.b64decode(s)
    except Exception: return None
    if raw[:8] != TD or len(raw) < 262: return None
    u = lambda o: int.from_bytes(raw[o:o + 8], "little")
    n = int.from_bytes(raw[258:262], "little"); o = 262 + n
    qm = raw[o + 37:o + 69]
    quote = None if len(qm) < 32 or qm == b"\0" * 32 else b58(qm)
    qamt = int.from_bytes(raw[o + 69:o + 77], "little") if quote and len(raw) >= o + 77 else None
    return dict(mint=b58(raw[8:40]), sol=u(40), tok=u(48), buy=raw[56] == 1, user=b58(raw[57:89]), vsol=u(97), vtok=u(105), fee=u(169), cfee=u(217),
                ix=raw[262:262 + n].decode("utf-8", "replace"), quote=quote, qamt=qamt)
