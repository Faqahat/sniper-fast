import json, urllib.request, os, time
TOK = os.environ["CONSTANTK_TOKEN"]
RPC = f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
W = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
WSOL = "So11111111111111111111111111111111111111112"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
WL = {"ipfs.io", "metadata.j7tracker.io", "m.rapidlaunch.io", "gateway.pinata.cloud"}
BL = {"gg.sc", "ipfs.launchblitz.ai", "pf.jake-98f.workers.dev", "ipfs2.extraction.live",
      "fast-ipfs.com", "storage.googleapis.com", "img.launchtracker4444.com", "gatewaypinata.online",
      "meta.uxento.io", "answering-afterwards-spoke-communication.trycloudflare.com"}


def b58dec(s):
    n = 0
    for c in s:
        n = n * 58 + B58.index(c)
    return n.to_bytes((n.bit_length() + 7) // 8, "big")


def rpc(m, p):
    req = urllib.request.Request(RPC, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"})
    for i in range(6):
        try:
            return json.load(urllib.request.urlopen(req, timeout=25)).get("result")
        except Exception:
            time.sleep(0.4 * (i + 1))
    return None


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


def host_of(uri):
    if not uri:
        return "?"
    s = uri.split("://", 1)[-1]
    return s.split("/", 1)[0]


def mint_host(mint):
    # oldest sig = create tx
    sgs = []
    before = None
    while True:
        prm = [mint, {"limit": 1000}] if before is None else [mint, {"limit": 1000, "before": before}]
        r = rpc("getSignaturesForAddress", prm)
        if not r:
            break
        sgs += r
        if len(r) < 1000:
            break
        before = r[-1]["signature"]
        if len(sgs) > 5000:
            break
    if not sgs:
        return None
    tx = rpc("getTransaction", [sgs[-1]["signature"], {"maxSupportedTransactionVersion": 0, "encoding": "jsonParsed"}])
    if not tx:
        return None
    msg = tx["transaction"]["message"]
    ixs = list(msg.get("instructions", []))
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
    if best is None:
        return None
    return host_of(parse_uri(best))


# collect his recent BUYS (token balance increased)
sigs = []
before = None
while len(sigs) < 400:
    prm = [W, {"limit": 200}] if before is None else [W, {"limit": 200, "before": before}]
    r = rpc("getSignaturesForAddress", prm)
    if not r:
        break
    sigs += r
    if len(r) < 200:
        break
    before = r[-1]["signature"]

buys = []  # (mint) newest first
seen = set()
for s in sigs:
    if len(buys) >= 30:
        break
    tx = rpc("getTransaction", [s["signature"], {"maxSupportedTransactionVersion": 0, "encoding": "jsonParsed"}])
    if not tx or not tx.get("meta") or tx["meta"].get("err"):
        continue
    pre = {b["mint"]: float(b["uiTokenAmount"]["uiAmount"] or 0) for b in tx["meta"].get("preTokenBalances", []) if b.get("owner") == W}
    post = {b["mint"]: float(b["uiTokenAmount"]["uiAmount"] or 0) for b in tx["meta"].get("postTokenBalances", []) if b.get("owner") == W}
    for mint in post:
        if mint == WSOL:
            continue
        if post[mint] - pre.get(mint, 0) > 0 and mint not in seen:
            seen.add(mint)
            buys.append(mint)
            break

print(f"his recent BUYS found: {len(buys)}")
print(f"{'mint':12} host")
tw = tb = to = 0
for mint in buys:
    h = mint_host(mint)
    tag = "TRUSTED" if h in WL else ("BOT-LAUNCHPAD" if h in BL else "other")
    if h in WL:
        tw += 1
    elif h in BL:
        tb += 1
    else:
        to += 1
    print(f"  {mint[:10]}  {h:40} {tag}")
n = len(buys)
if n:
    print(f"\nTRUSTED(whitelist): {tw}/{n} = {tw/n*100:.0f}%  |  BOT-LAUNCHPAD(blacklist): {tb}/{n} = {tb/n*100:.0f}%  |  other: {to}/{n}")
