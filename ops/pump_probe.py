import json, os, urllib.request, urllib.error, time

RPC = os.environ["RPC_URL"]
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
BUY = bytes.fromhex("38fc74089edfcd5f")
SELL = bytes.fromhex("33e685a4017f83ad")

ALPH = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n = 0
    for c in s:
        n = n * 58 + ALPH.index(c)
    full = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    pad = len(s) - len(s.lstrip("1"))
    return b"\x00" * pad + full

def rpc(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for attempt in range(8):
        req = urllib.request.Request(RPC, data=body, headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.load(r).get("result")
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(1.0 + attempt * 1.5)
                continue
            raise
    raise RuntimeError(f"{method}: still 429 after retries")

def writable_set(msg, n_static, n_lw, n_lr):
    h = msg["header"]
    S, rs, ru = h["numRequiredSignatures"], h["numReadonlySignedAccounts"], h["numReadonlyUnsignedAccounts"]
    w = set()
    for i in range(n_static):
        if i < S:
            if i < S - rs: w.add(i)
        else:
            if i < n_static - ru: w.add(i)
    for i in range(n_static, n_static + n_lw): w.add(i)
    return w

def full_keys(tx):
    msg = tx["transaction"]["message"]
    static = msg["accountKeys"]
    la = tx.get("meta", {}).get("loadedAddresses") or {"writable": [], "readonly": []}
    keys = list(static) + list(la["writable"]) + list(la["readonly"])
    wset = writable_set(msg, len(static), len(la["writable"]), len(la["readonly"]))
    return msg, keys, wset

sigs = rpc("getSignaturesForAddress", [PUMP, {"limit": 1000}])
print(f"fetched {len(sigs)} signatures")

buys, sells = [], []
for s in sigs:
    if s.get("err") is not None:
        continue
    if len(buys) >= 4 and len(sells) >= 3:
        break
    time.sleep(0.35)
    tx = rpc("getTransaction", [s["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}])
    if not tx or tx.get("meta", {}).get("err") is not None:
        continue
    msg, keys, wset = full_keys(tx)
    for ix in msg["instructions"]:
        prog = keys[ix["programIdIndex"]]
        if prog != PUMP:
            continue
        data = b58d(ix["data"])
        disc = data[:8]
        accs = ix["accounts"]
        if disc == BUY and len(buys) < 4:
            buys.append((s["signature"], accs, keys, wset))
        elif disc == SELL and len(sells) < 3:
            sells.append((s["signature"], accs, keys, wset))

def show(label, rows):
    for sig, accs, keys, wset in rows:
        print(f"\n== {label} {sig[:20]} nacct={len(accs)} ==")
        for pos, idx in enumerate(accs):
            w = "W" if idx in wset else "r"
            print(f"  [{pos:>2}] {w} {keys[idx]}")

show("BUY", buys)
show("SELL", sells)

print("\n===== ANALYSIS =====")
def tail(rows, i):
    out = []
    for sig, accs, keys, wset in rows:
        if len(accs) > i:
            out.append((keys[accs[i]], "W" if accs[i] in wset else "r"))
    return out

print("BUY  acct[2] mint  :", [keys[accs[2]] for _, accs, keys, _ in buys if len(accs) > 2])
print("BUY  acct[1] feeRcp:", [(keys[accs[1]], "W" if accs[1] in w else "r") for _, accs, keys, w in buys if len(accs) > 1])
print("BUY  acct[16]      :", tail(buys, 16))
print("BUY  acct[17]      :", tail(buys, 17))
print("SELL acct[1] feeRcp:", [(keys[accs[1]], "W" if accs[1] in w else "r") for _, accs, keys, w in sells if len(accs) > 1])
print("SELL nacct         :", [len(accs) for _, accs, _, _ in sells])
print("SELL acct[14]      :", tail(sells, 14))
print("SELL acct[15]      :", tail(sells, 15))
print("SELL acct[16]      :", tail(sells, 16))
