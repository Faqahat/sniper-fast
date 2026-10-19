# READ-ONLY helpers for the det audit (2026-10-18). RPC with a process-wide rate limiter + 429 backoff (from
# /root/nob/nrpc.py), base58, pump.fun event parsing (full CreateEvent / TradeEvent), engine-equivalent dev-buy reads.
import json, os, time, threading, urllib.request, urllib.error, random, base64, hashlib

TOK = os.environ.get("CONSTANTK_TOKEN", "")
URL = f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
RPS = float(os.environ.get("DET_RPS", "12"))
_lock = threading.Lock()
_next = [0.0]
stats = {"calls": 0, "r429": 0, "err": 0}

PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
MINT_AUTH = "TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM"
WSOL = "So11111111111111111111111111111111111111112"
T22 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
SPL = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
VOTE = "Vote111111111111111111111111111111111111111"
W4 = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
OURS = "FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS"
VQ0, VT0 = 30_000_000_000, 1_073_000_000_000_000
CREATE_V2 = bytes([0xd6, 0x90, 0x4c, 0xec, 0x5f, 0x8b, 0x31, 0xb4])
CREATE = bytes([0x18, 0x1e, 0xc8, 0x28, 0x05, 0x1c, 0x07, 0x77])
SIZED = {bytes([0xe1, 0xf7, 0x50, 0x1e, 0xd5, 0xb3, 0x84, 0x88]): "quote_in_v3", bytes([0xc2, 0xab, 0x1c, 0x46, 0x68, 0x4d, 0x5b, 0x2f]): "quote_in_v2",
         bytes([0x38, 0xfc, 0x74, 0x08, 0x9e, 0xdf, 0xcd, 0x5f]): "exact_sol_in"}
CAP = {bytes([0x66, 0x06, 0x3d, 0x12, 0x01, 0xda, 0xeb, 0xea]): "buy", bytes([0xb8, 0x17, 0xee, 0x61, 0x67, 0xc5, 0xd3, 0x3d]): "buy_v2",
       bytes([0x07, 0x05, 0x1d, 0xc4, 0xf5, 0x17, 0x65, 0x50]): "buy_v3"}
TRADE_DISC = bytes([189, 219, 127, 211, 78, 230, 97, 238])
CREATE_EV = hashlib.sha256(b"event:CreateEvent").digest()[:8]
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
B58I = {c: i for i, c in enumerate(B58)}
BOT_HOSTS = {"gg.sc", "ipfs.launchblitz.ai", "pf.jake-98f.workers.dev", "storage.googleapis.com"}


def _wait():
    with _lock:
        now = time.time()
        t = max(now, _next[0])
        _next[0] = t + 1.0 / RPS
    d = t - time.time()
    if d > 0:
        time.sleep(d)


def rpc(m, p, tries=12, timeout=60):
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode()
    last = None
    for i in range(tries):
        _wait()
        stats["calls"] += 1
        try:
            req = urllib.request.Request(URL, data=data, headers={"content-type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=timeout))
            if "error" in r:
                code = r["error"].get("code")
                if code in (-32007, -32009, -32004, -32020) and i >= 1:
                    return {"__err": code, "msg": str(r["error"])[:150]}
                last = r["error"]
                time.sleep(0.5 * (i + 1))
                continue
            return r.get("result")
        except urllib.error.HTTPError as ex:
            last = ex
            if ex.code == 429:
                stats["r429"] += 1
                time.sleep(min(8, 0.4 * 2 ** min(i, 4)) + random.random() * 0.5)
            else:
                time.sleep(0.5 * (i + 1))
        except Exception as ex:
            last = ex
            stats["err"] += 1
            time.sleep(0.5 * (i + 1))
    return {"__err": str(last)[:200]}


def b58dec(s):
    n = 0
    for c in s:
        n = n * 58 + B58I[c]
    pad = len(s) - len(s.lstrip("1"))
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\x00" * pad + b


def b58enc(b):
    n = int.from_bytes(b, "big")
    out = []
    while n:
        n, r = divmod(n, 58)
        out.append(B58[r])
    pad = len(b) - len(b.lstrip(b"\x00"))
    return "1" * pad + "".join(reversed(out))


class Rd:
    def __init__(s, b, o=0): s.b, s.o = b, o
    def u8(s): v = s.b[s.o]; s.o += 1; return v
    def u64(s): v = int.from_bytes(s.b[s.o:s.o + 8], "little"); s.o += 8; return v
    def i64(s): v = int.from_bytes(s.b[s.o:s.o + 8], "little", signed=True); s.o += 8; return v
    def pk(s): v = b58enc(s.b[s.o:s.o + 32]); s.o += 32; return v
    def st(s):
        n = int.from_bytes(s.b[s.o:s.o + 4], "little"); s.o += 4
        v = s.b[s.o:s.o + n].decode("utf8", "replace"); s.o += n; return v
    def left(s): return len(s.b) - s.o


def parse_create_event(raw):
    r = Rd(raw, 8)
    e = {}
    try:
        e["name"], e["symbol"], e["uri"] = r.st(), r.st(), r.st()
        e["mint"], e["bonding_curve"], e["user"], e["creator"] = r.pk(), r.pk(), r.pk(), r.pk()
        e["timestamp"] = r.i64()
        e["vtok"], e["vsol"], e["rtok"], e["supply"] = r.u64(), r.u64(), r.u64(), r.u64()
        if r.left() >= 32: e["token_program"] = r.pk()
        if r.left() >= 1: e["mayhem"] = bool(r.u8())
        if r.left() >= 1: e["cashback"] = bool(r.u8())
        if r.left() >= 32: e["quote_mint"] = r.pk()
        if r.left() >= 8: e["vquote"] = r.u64()
        if r.left() >= 8: e["fee_bps"] = r.u64()
        if r.left() >= 1: e["holder"] = bool(r.u8())
        if r.left() >= 1: e["depth"] = r.u8()
    except Exception as ex:
        e["parse_err"] = str(ex)[:80]
    return e


def parse_trade_event(raw):
    r = Rd(raw, 8)
    e = {}
    try:
        e["mint"], e["sol"], e["tok"], e["buy"], e["user"] = r.pk(), r.u64(), r.u64(), bool(r.u8()), r.pk()
        e["ts"], e["vsol"], e["vtok"] = r.i64(), r.u64(), r.u64()
    except Exception as ex:
        e["parse_err"] = str(ex)[:80]
    return e


def events(logs):
    tr, cr = [], []
    for l in logs or []:
        if not l.startswith("Program data: "):
            continue
        try:
            raw = base64.b64decode(l[14:] + "===")
        except Exception:
            continue
        if raw[:8] == TRADE_DISC and len(raw) >= 129:
            tr.append(parse_trade_event(raw))
        elif raw[:8] == CREATE_EV:
            cr.append(parse_create_event(raw))
    return tr, cr


def parse_create_args(data):
    """mirror of snipe.rs parse_create_args (fixed layout: mayhem u8, cashback u8, fee u64, holder u8)."""
    p = 8
    for _ in range(3):
        if len(data) < p + 4:
            return {}
        n = int.from_bytes(data[p:p + 4], "little")
        p += 4 + n
    a = {"creator": b58enc(data[p:p + 32]) if len(data) >= p + 32 else None, "trailing": len(data) - (p + 32)}
    p += 32
    a["mayhem"] = data[p] != 0 if len(data) > p else False
    a["cashback"] = data[p + 1] != 0 if len(data) > p + 1 else False
    a["fee_bps"] = int.from_bytes(data[p + 2:p + 10], "little") if len(data) >= p + 10 else 0
    a["holder"] = data[p + 10] != 0 if len(data) > p + 10 else False
    a["uri"] = None
    return a


def create_uri(data):
    p = 8
    out = []
    for _ in range(3):
        n = int.from_bytes(data[p:p + 4], "little")
        out.append(data[p + 4:p + 4 + n].decode("utf8", "replace"))
        p += 4 + n
    return out[2] if len(out) == 3 else ""


def host_of(uri):
    return uri.split("://")[-1].split("/")[0] if uri else ""


def is_bot_host(h):
    return h in BOT_HOSTS or h.endswith(".trycloudflare.com")


def cap_cost(vq, vt, t):
    """SOL (lamports) to buy t tokens on a curve (vq, vt): ceil(vq*vt/(vt-t)) - vq."""
    if t <= 0 or t >= vt:
        return 0, vq, vt
    nvt = vt - t
    nvq = -(-(vq * vt) // nvt)
    return nvq - vq, nvq, nvt
