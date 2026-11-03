#!/usr/bin/env python3
"""pump.fun TradeEvent decoder for the collect tx records (field `ev`, base64 anchor event data)."""
import base64, struct

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58(b):
    n = int.from_bytes(b, "big")
    s = ""
    while n:
        n, r = divmod(n, 58)
        s = B58[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s


TRADE_DISC = bytes.fromhex("bddb7fd34ee661ee")


def decode(e):
    """-> dict or None. Layout after the 8-byte discriminator:
    mint(32) solAmount(u64) tokenAmount(u64) isBuy(1) user(32) timestamp(i64) vSol(u64) vTok(u64)"""
    try:
        raw = base64.b64decode(e)
    except Exception:
        return None
    if raw[:8] != TRADE_DISC or len(raw) < 113:
        return None
    o = 8
    mint = raw[o:o + 32]; o += 32
    sol, tok = struct.unpack_from("<QQ", raw, o); o += 16
    is_buy = raw[o]; o += 1
    user = raw[o:o + 32]; o += 32
    ts, = struct.unpack_from("<q", raw, o); o += 8
    vsol, vtok = struct.unpack_from("<QQ", raw, o)
    if is_buy not in (0, 1) or vsol == 0 or vtok == 0:
        return None
    return dict(mint=b58(mint), sol=sol, tok=tok, buy=bool(is_buy), user=b58(user), ts=ts, vsol=vsol, vtok=vtok)
