"""Read-only mainnet RPC helper for the arbx-sizing layout checks: rate-limited (<= 2.5 req/s) and cached on disk
(program/venue-harness/fixtures/rpc-cache), so re-running never re-queries. Also base58 and PDA derivation."""
import base64, hashlib, json, os, time, urllib.request

RPC = "https://api.mainnet-beta.solana.com"
CACHE = os.path.join(os.path.dirname(__file__), "..", "..", "venue-harness", "fixtures", "rpc-cache")
_last = [0.0]

def rpc(method, params, cache=True):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, sort_keys=True)
    path = os.path.join(CACHE, f"{method}-{hashlib.sha256(body.encode()).hexdigest()[:20]}.json")
    if cache and os.path.exists(path):
        return json.load(open(path))["result"]
    for attempt in range(5):
        wait = 0.4 - (time.time() - _last[0])
        if wait > 0: time.sleep(wait)
        _last[0] = time.time()
        req = urllib.request.Request(RPC, data=body.encode(), headers={"Content-Type": "application/json"})
        try:
            out = json.load(urllib.request.urlopen(req, timeout=30))
        except Exception as e:  # 429 etc: back off
            time.sleep(2 + 2 * attempt); continue
        if "error" in out:
            raise RuntimeError(f"{method}: {out['error']}")
        os.makedirs(CACHE, exist_ok=True)
        json.dump({"request": json.loads(body), "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "result": out["result"]}, open(path, "w"))
        return out["result"]
    raise RuntimeError(f"{method}: gave up")

ALPH = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n = 0
    for c in s: n = n * 58 + ALPH.index(c)
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b
def b58e(b):
    n = int.from_bytes(b, "big"); s = ""
    while n: n, r = divmod(n, 58); s = ALPH[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s
def pk(s):
    b = b58d(s); return b.rjust(32, b"\0")

# ed25519 point decompression: is a 32-byte string a point on the curve?
_P = 2**255 - 19; _D = -121665 * pow(121666, _P - 2, _P) % _P; _I = pow(2, (_P - 1) // 4, _P)
def on_curve(b):
    y = int.from_bytes(b, "little") & ((1 << 255) - 1)
    if y >= _P: return False
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    if x2 == 0: return True
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0: x = x * _I % _P
    return (x * x - x2) % _P == 0
def pda(seeds, program):
    for bump in range(255, -1, -1):
        h = hashlib.sha256(b"".join(seeds) + bytes([bump]) + pk(program) + b"ProgramDerivedAddress").digest()
        if not on_curve(h): return b58e(h), bump
    raise ValueError("no bump")

def accounts(keys):
    """getMultipleAccounts (base64), in chunks of 100. Returns {key: (owner, lamports, data bytes) or None} and the slot."""
    out, slot = {}, None
    for i in range(0, len(keys), 100):
        r = rpc("getMultipleAccounts", [keys[i:i + 100], {"encoding": "base64", "commitment": "confirmed"}])
        slot = r["context"]["slot"]
        for k, a in zip(keys[i:i + 100], r["value"]):
            out[k] = None if a is None else (a["owner"], a["lamports"], base64.b64decode(a["data"][0]))
    return out, slot

u8 = lambda d, o: d[o]
u16 = lambda d, o: int.from_bytes(d[o:o + 2], "little")
u32 = lambda d, o: int.from_bytes(d[o:o + 4], "little")
i32 = lambda d, o: int.from_bytes(d[o:o + 4], "little", signed=True)
u64 = lambda d, o: int.from_bytes(d[o:o + 8], "little")
i64 = lambda d, o: int.from_bytes(d[o:o + 8], "little", signed=True)
u128 = lambda d, o: int.from_bytes(d[o:o + 16], "little")
i128 = lambda d, o: int.from_bytes(d[o:o + 16], "little", signed=True)
key = lambda d, o: b58e(d[o:o + 32]).rjust(32, "1") if False else b58e(d[o:o + 32])
disc = lambda name: hashlib.sha256(f"account:{name}".encode()).digest()[:8]
