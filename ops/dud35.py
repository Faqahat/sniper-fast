import json, urllib.request, os, time, hashlib, base64, re, datetime
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


def rpc(m, p):
    req = urllib.request.Request(RPC, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"})
    for i in range(6):
        try:
            return json.load(urllib.request.urlopen(req, timeout=25)).get("result")
        except Exception:
            time.sleep(0.3 * (i + 1))
    return None


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


def parse_uri(raw):
    p = 8
    uri = None
    for i in range(3):
        if p + 4 > len(raw):
            return None
        ln = int.from_bytes(raw[p:p + 4], "little")
        start = p + 4
        end = start + ln
        if end > len(raw):
            return None
        if i == 2:
            uri = raw[start:end].decode("utf-8", "replace")
        p = end
    return uri


def info(mint):
    # oldest sig = create
    r = rpc("getSignaturesForAddress", [mint, {"limit": 1000}])
    if not r:
        return None
    oldest = r
    while len(oldest) == 1000:
        nxt = rpc("getSignaturesForAddress", [mint, {"limit": 1000, "before": oldest[-1]["signature"]}])
        if not nxt:
            break
        oldest = nxt
    csig = oldest[-1]
    tx = rpc("getTransaction", [csig["signature"], {"maxSupportedTransactionVersion": 0, "encoding": "jsonParsed"}])
    if not tx:
        return None
    keys = tx["transaction"]["message"]["accountKeys"]
    feepayer = next((k["pubkey"] for k in keys if k.get("signer")), "?")
    ixs = list(tx["transaction"]["message"].get("instructions", []))
    for inner in tx["meta"].get("innerInstructions", []):
        ixs += inner["instructions"]
    best = None
    for ix in ixs:
        if ix.get("programId") == PUMP and "data" in ix:
            try:
                raw = b58dec(ix["data"])
            except Exception:
                continue
            if best is None or len(raw) > len(best):
                best = raw
    uri = parse_uri(best) if best else ""
    # creator from bonding curve
    ai = rpc("getAccountInfo", [bc(mint), {"encoding": "base64"}])
    creator = "?"
    if ai and ai.get("value"):
        rawb = base64.b64decode(ai["value"]["data"][0])
        if len(rawb) >= 81:
            creator = b58enc(rawb[49:81])
    bt = csig.get("blockTime", 0)
    return {"feepayer": feepayer, "uri": uri, "creator": creator, "bt": bt}


# collect dev~3.5 duds from paper log
cand = {}
for ln in open("/root/arbx-fast/paper_urihost.log"):
    m = re.search(r"PAPER launch #\d+ slot=\d+ mint=(\w+) dev_buy=(\d+)", ln)
    if m:
        cand[m.group(1)] = {"dev": int(m.group(2))}
    m = re.search(r"PAPER done mint=(\w+).*peak_r=([0-9.]+)", ln)
    if m and m.group(1) in cand:
        cand[m.group(1)]["peak"] = float(m.group(2))
duds = [(k, v["dev"], v.get("peak")) for k, v in cand.items() if 3.3e9 <= v["dev"] <= 3.7e9 and v.get("peak", 9) <= 1.1]
print(f"dev~3.5 duds: {len(duds)}")
print("mint      dev_lamports  peak  feepayer(relayer)  uri_host           creator    time")
feepayers = {}
hosts = {}
devs = {}
for mint, dev, peak in duds:
    inf = info(mint)
    if not inf:
        print(f"  {mint[:8]} (no info)")
        continue
    host = inf["uri"].split("://", 1)[-1].split("/", 1)[0] if inf["uri"] else "?"
    t = datetime.datetime.utcfromtimestamp(inf["bt"]).strftime("%m-%d %H:%M") if inf["bt"] else "?"
    print(f"  {mint[:8]}  {dev:>11}  {peak:.2f}  {inf['feepayer'][:10]}  {host:18} {inf['creator'][:8]}  {t}")
    feepayers[inf["feepayer"]] = feepayers.get(inf["feepayer"], 0) + 1
    hosts[host] = hosts.get(host, 0) + 1
    devs[dev] = devs.get(dev, 0) + 1
print("\nfee-payers (relayers):", feepayers)
print("hosts:", hosts)
print("exact dev amounts:", devs)
