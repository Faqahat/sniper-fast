import json, os, urllib.request, urllib.error, time
from collections import Counter

RPC = os.environ["RPC_URL"]
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
ALPH = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n = 0
    for c in s: n = n * 58 + ALPH.index(c)
    full = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\x00" * (len(s) - len(s.lstrip("1"))) + full

def rpc(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for attempt in range(8):
        try:
            with urllib.request.urlopen(urllib.request.Request(RPC, data=body, headers={"content-type": "application/json"}), timeout=45) as r:
                return json.load(r).get("result")
        except urllib.error.HTTPError as e:
            if e.code == 429: time.sleep(1.0 + attempt * 1.5); continue
            raise
    raise RuntimeError("429")

def writable_set(msg, ns, nlw):
    h = msg["header"]; S, rs, ru = h["numRequiredSignatures"], h["numReadonlySignedAccounts"], h["numReadonlyUnsignedAccounts"]
    w = set()
    for i in range(ns):
        if i < S:
            if i < S - rs: w.add(i)
        elif i < ns - ru: w.add(i)
    for i in range(ns, ns + nlw): w.add(i)
    return w

def full(tx):
    msg = tx["transaction"]["message"]; static = msg["accountKeys"]
    la = tx.get("meta", {}).get("loadedAddresses") or {"writable": [], "readonly": []}
    return msg, list(static) + la["writable"] + la["readonly"], writable_set(msg, len(static), len(la["writable"]))

def pump_ixs(tx):
    """yield (data_bytes, [account_indices]) for every pump ix, top-level and inner."""
    msg, keys, wset = full(tx)
    out = []
    for ix in msg["instructions"]:
        if keys[ix["programIdIndex"]] == PUMP:
            out.append((b58d(ix["data"]), ix["accounts"]))
    for inner in tx.get("meta", {}).get("innerInstructions", []) or []:
        for ix in inner["instructions"]:
            if keys[ix["programIdIndex"]] == PUMP:
                out.append((b58d(ix["data"]), ix["accounts"]))
    return keys, wset, out

sigs = rpc("getSignaturesForAddress", [PUMP, {"limit": 400}])
disc_counter = Counter()
examples = {}  # disc_hex -> list of (sig, keys, wset, accs, data)
n_ok = 0
for s in sigs:
    if s.get("err") is not None: continue
    if n_ok >= 60: break
    time.sleep(0.3)
    try:
        tx = rpc("getTransaction", [s["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}])
    except Exception:
        continue
    if not tx or tx.get("meta", {}).get("err") is not None: continue
    n_ok += 1
    keys, wset, ixs = pump_ixs(tx)
    for data, accs in ixs:
        disc = data[:8].hex()
        disc_counter[disc] += 1
        examples.setdefault(disc, [])
        if len(examples[disc]) < 3:
            examples[disc].append((s["signature"], keys, wset, accs, data))

print(f"scanned {n_ok} successful pump txs")
print("\npump instruction discriminators seen (disc_hex: count):")
for disc, c in disc_counter.most_common():
    print(f"  {disc}  x{c}")

# known buy discs
NAMES = {"38fc74089edfcd5f": "buy_exact_sol_in", "66063d1201daebea": "buy", "b817ee61d6e5f6d6": "buy_v2(?)",
         "33e685a4017f83ad": "sell", "102b0c82b5d0e2ff": "sell_v2(?)"}
def name(d): return NAMES.get(d, "?")

# dump full detail for the most common buy-ish discs (those that look like buys: >=14 accounts)
print("\n===== EXAMPLES (full account list + data) for each disc =====")
for disc, exs in examples.items():
    sig, keys, wset, accs, data = exs[0]
    print(f"\ndisc {disc} ({name(disc)})  count={disc_counter[disc]}  nacct={len(accs)} datalen={len(data)}")
    print(f"  ref sig {sig}")
    print(f"  data hex {data.hex()}")
    if len(data) >= 24:
        import struct
        a1 = struct.unpack_from('<Q', data, 8)[0]
        a2 = struct.unpack_from('<Q', data, 16)[0]
        tail = data[24:].hex()
        print(f"  arg1(@8)={a1} arg2(@16)={a2} tail(@24)={tail!r}")
    for pos, idx in enumerate(accs):
        print(f"    [{pos:>2}] {'W' if idx in wset else 'r'} {keys[idx]}")
