# pump TradeEvent / CreateEvent parsing incl. fee bps. READ-ONLY.
import base64, hashlib
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
TRADE_DISC = bytes([189, 219, 127, 211, 78, 230, 97, 238])
CREATE_DISC = hashlib.sha256(b"event:CreateEvent").digest()[:8]
def b58enc(b):
    n = int.from_bytes(b, "big"); out = []
    while n:
        n, r = divmod(n, 58); out.append(B58[r])
    pad = len(b) - len(b.lstrip(b"\x00"))
    return "1" * pad + "".join(reversed(out))
def u64(raw, o): return int.from_bytes(raw[o:o + 8], "little")
def parse_trade(raw):
    o = 8
    mint = b58enc(raw[o:o + 32]); o += 32
    sol = u64(raw, o); tok = u64(raw, o + 8); isb = raw[o + 16]; user = b58enc(raw[o + 17:o + 49]); ts = u64(raw, o + 49)
    p = o + 57
    vsol, vtok, rsol, rtok = (u64(raw, p + 8 * i) for i in range(4))
    p += 32 + 32
    fbps = u64(raw, p) if len(raw) >= p + 8 else None
    p += 16 + 32
    cbps = u64(raw, p) if len(raw) >= p + 8 else None
    return dict(mint=mint, sol=sol, tok=tok, buy=isb, user=user, ts=ts, vsol=vsol, vtok=vtok, rsol=rsol, fbps=fbps, cbps=cbps)
def parse_create(raw):
    try:
        o = 8; strs = []
        for _ in range(3):
            n = int.from_bytes(raw[o:o + 4], "little"); o += 4
            strs.append(raw[o:o + n].decode("utf8", "replace")); o += n
        mint = b58enc(raw[o:o + 32]); o += 32
        o += 32
        user = b58enc(raw[o:o + 32]); o += 32
        creator = b58enc(raw[o:o + 32]) if len(raw) >= o + 32 else user
        return dict(name=strs[0][:40], symbol=strs[1][:20], mint=mint, user=user, creator=creator)
    except Exception:
        return None
def events(logs):
    tr, cr = [], []
    for l in logs or []:
        if l.startswith("Program data: "):
            try: raw = base64.b64decode(l[14:] + "===")
            except Exception: continue
            if raw[:8] == TRADE_DISC and len(raw) >= 8 + 57 + 32:
                tr.append(parse_trade(raw))
            elif raw[:8] == CREATE_DISC:
                c = parse_create(raw)
                if c: cr.append(c)
    return tr, cr
