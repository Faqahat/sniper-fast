"""pump.fun TradeEvent decoder (event bytes without the 8-byte CPI prefix, as stored in 'ev')."""
import base64, struct
def b58(b):
    A = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"; n = int.from_bytes(b, "big"); s = ""
    while n: n, r = divmod(n, 58); s = A[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s
def dec(e64):
    b = base64.b64decode(e64)
    if b[:8].hex() != "bddb7fd34ee661ee": return None
    o = 8; d = {}
    def u64():
        nonlocal o; v = struct.unpack_from("<Q", b, o)[0]; o += 8; return v
    def pk():
        nonlocal o; v = b58(b[o:o + 32]); o += 32; return v
    d["mint"] = pk(); d["sol"] = u64(); d["tok"] = u64(); d["is_buy"] = b[o]; o += 1; d["user"] = pk(); d["ts"] = u64()
    d["vsr"] = u64(); d["vtr"] = u64(); d["rsr"] = u64(); d["rtr"] = u64(); d["fee_rcpt"] = pk(); d["fee_bps"] = u64(); d["fee"] = u64()
    d["creator"] = pk(); d["cfee_bps"] = u64(); d["cfee"] = u64(); d["track"] = b[o]; o += 1
    d["unclaimed"] = u64(); d["claimed"] = u64(); d["cur_vol"] = u64(); d["last_upd"] = u64()
    L = struct.unpack_from("<I", b, o)[0]; o += 4; d["ix"] = b[o:o + L].decode(errors="replace"); o += L
    d["rest"] = b[o:].hex(); d["rest_u64"] = [struct.unpack_from("<Q", b, o + 1 + 8 * k)[0] for k in range((len(b) - o - 1) // 8)]
    return d
