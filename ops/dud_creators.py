import json, urllib.request, os, time, hashlib, base64
TOK = os.environ["CONSTANTK_TOKEN"]
RPC = f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
PUMP_STR = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58dec(s):
    n = 0
    for c in s:
        n = n * 58 + B58.index(c)
    return n.to_bytes((n.bit_length() + 7) // 8, "big")


def b58enc(b):
    n = int.from_bytes(b, "big")
    o = ""
    while n > 0:
        n, r = divmod(n, 58)
        o = B58[r] + o
    return "1" * (len(b) - len(b.lstrip(b"\x00"))) + o


P = 2**255 - 19


def oc(yb):
    y = int.from_bytes(yb, "little") & ((1 << 255) - 1)
    if y >= P:
        return False
    d = (-121665 * pow(121666, P - 2, P)) % P
    u = (y * y - 1) % P
    v = (d * y * y + 1) % P
    xx = (u * pow(v, P - 2, P)) % P
    x = pow(xx, (P + 3) // 8, P)
    if (x * x - xx) % P != 0:
        x = (x * pow(2, (P - 1) // 4, P)) % P
    return (x * x - xx) % P == 0


PUMP = b58dec(PUMP_STR)


def bc(m):
    s = b"bonding-curve" + b58dec(m)
    for b in range(255, -1, -1):
        h = hashlib.sha256(s + bytes([b]) + PUMP + b"ProgramDerivedAddress").digest()
        if not oc(h):
            return b58enc(h)


def rpc(m, p):
    req = urllib.request.Request(RPC, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"})
    for i in range(6):
        try:
            return json.load(urllib.request.urlopen(req, timeout=25)).get("result")
        except Exception:
            time.sleep(0.4 * (i + 1))
    return None


def creator_of(mint):
    ai = rpc("getAccountInfo", [bc(mint), {"encoding": "base64"}])
    if not ai or not ai.get("value"):
        return None
    raw = base64.b64decode(ai["value"]["data"][0])
    if len(raw) < 81:
        return None
    return b58enc(raw[49:81])  # creator field at offset 49


def count_tokens(creator):
    # getProgramAccounts memcmp at offset 49 = creator
    r = rpc("getProgramAccounts", [PUMP_STR, {"encoding": "base64", "filters": [{"memcmp": {"offset": 49, "bytes": creator}}], "dataSlice": {"offset": 0, "length": 0}}])
    return len(r) if r else "?"


MINTS = ["6YuuWVUnvbB52jyD3DybQxqj4NivyBqLgaXfPuyfpump",
         "7pgW5odugicKZp9JaQFkhc6BRHP6UNbeDjRMQtLQpump",
         "5QVMCsGcMu7TsjuWcfLq8o5VFSPubcjQJ9VEri39pump",
         "Ga53pn23cV6TvJUzEHRto12uibe6vjXweK1PYhBrpump",
         "3XSyoX2XnrqzJ6Z2dMZGoM2azXhsuxNWkzLSy884pump"]
creators = {}
for m in MINTS:
    c = creator_of(m)
    creators[m] = c
    print(f"{m[:10]}  creator={c}")
uniq = set(v for v in creators.values() if v)
print(f"\nunique creators among these {len(MINTS)} duds: {len(uniq)}")
for c in uniq:
    which = [m[:8] for m, v in creators.items() if v == c]
    print(f"  {c}  -> {len(which)} of these tokens; lifetime pump tokens by this creator: {count_tokens(c)}  ({which})")
