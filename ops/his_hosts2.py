import json, urllib.request, os, time, concurrent.futures as cf
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
            time.sleep(0.3 * (i + 1))
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
    return uri.split("://", 1)[-1].split("/", 1)[0]


def gettx(sig):
    return rpc("getTransaction", [sig, {"maxSupportedTransactionVersion": 0, "encoding": "jsonParsed"}])


def bought_mint(tx):
    if not tx or not tx.get("meta") or tx["meta"].get("err"):
        return None
    pre = {b["mint"]: float(b["uiTokenAmount"]["uiAmount"] or 0) for b in tx["meta"].get("preTokenBalances", []) if b.get("owner") == W}
    post = {b["mint"]: float(b["uiTokenAmount"]["uiAmount"] or 0) for b in tx["meta"].get("postTokenBalances", []) if b.get("owner") == W}
    for mint in post:
        if mint != WSOL and post[mint] - pre.get(mint, 0) > 0:
            return mint
    return None


def mint_host(mint):
    r = rpc("getSignaturesForAddress", [mint, {"limit": 1000}])
    if not r:
        return "?"
    oldest = r
    while len(oldest) == 1000:
        nxt = rpc("getSignaturesForAddress", [mint, {"limit": 1000, "before": oldest[-1]["signature"]}])
        if not nxt:
            break
        oldest = nxt
    tx = gettx(oldest[-1]["signature"])
    if not tx:
        return "?"
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
    return host_of(parse_uri(best)) if best else "?"


# recent sigs
sigs = []
before = None
while len(sigs) < 300:
    prm = [W, {"limit": 300}] if before is None else [W, {"limit": 300, "before": before}]
    r = rpc("getSignaturesForAddress", prm)
    if not r:
        break
    sigs += r
    if len(r) < 300:
        break
    before = r[-1]["signature"]

# parallel buy detection, preserve order (newest first)
txs = [None] * len(sigs)
with cf.ThreadPoolExecutor(max_workers=12) as ex:
    futs = {ex.submit(gettx, s["signature"]): i for i, s in enumerate(sigs)}
    for f in cf.as_completed(futs):
        txs[futs[f]] = f.result()

buys = []
seen = set()
for tx in txs:
    if len(buys) >= 30:
        break
    m = bought_mint(tx)
    if m and m not in seen:
        seen.add(m)
        buys.append(m)

print(f"his recent BUYS found: {len(buys)}")
hosts = {}
with cf.ThreadPoolExecutor(max_workers=10) as ex:
    for m, h in zip(buys, ex.map(mint_host, buys)):
        hosts[m] = h
tw = tb = to = 0
for m in buys:
    h = hosts[m]
    tag = "TRUSTED" if h in WL else ("BOT-LAUNCHPAD" if h in BL else "other")
    tw += h in WL
    tb += h in BL
    to += (h not in WL and h not in BL)
    print(f"  {m[:10]}  {h:42} {tag}")
n = len(buys)
if n:
    print(f"\nTRUSTED(whitelist): {tw}/{n}={tw/n*100:.0f}%  BOT-LAUNCHPAD: {tb}/{n}={tb/n*100:.0f}%  other: {to}/{n}={to/n*100:.0f}%")
