import json, urllib.request, os, time, re, concurrent.futures as cf
TOK = os.environ["CONSTANTK_TOKEN"]
RPC = f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58dec(s):
    n = 0
    for c in s:
        n = n * 58 + B58.index(c)
    return n.to_bytes((n.bit_length() + 7) // 8, "big")


def rpc(m, p):
    req = urllib.request.Request(RPC, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"})
    for i in range(4):
        try:
            return json.load(urllib.request.urlopen(req, timeout=15)).get("result")
        except Exception:
            time.sleep(0.3 * (i + 1))
    return None


def get_name(mint):
    # oldest sig; HARD cap 2 pages — skip graduated monsters
    sgs = []
    before = None
    pages = 0
    while pages < 2:
        prm = [mint, {"limit": 1000}] if before is None else [mint, {"limit": 1000, "before": before}]
        r = rpc("getSignaturesForAddress", prm)
        if not r:
            break
        sgs += r
        pages += 1
        if len(r) < 1000:
            break
        before = r[-1]["signature"]
    if pages >= 2 and len(sgs) >= 2000:
        return "(too-big)"
    if not sgs:
        return None
    tx = rpc("getTransaction", [sgs[-1]["signature"], {"maxSupportedTransactionVersion": 0, "encoding": "jsonParsed"}])
    if not tx:
        return None
    ixs = list(tx["transaction"]["message"].get("instructions", []))
    for inner in tx["meta"].get("innerInstructions", []):
        ixs += inner["instructions"]
    for ix in ixs:
        if ix.get("programId") == PUMP and "data" in ix:
            raw = b58dec(ix["data"])
            if len(raw) > 60:
                ln = int.from_bytes(raw[8:12], "little")
                return raw[12:12 + ln].decode("utf-8", "replace")
    return None


launch = {}
for ln in open("/root/arbx-fast/paper_blacklist.log"):
    m = re.search(r"PAPER launch #\d+ slot=\d+ mint=(\w+) dev_buy=(\d+)", ln)
    if m and m.group(1) not in launch:
        launch[m.group(1)] = {"dev": int(m.group(2))}
    m = re.search(r"PAPER done mint=(\w+).*peak_r=([0-9.]+).*@1.00=([+-][0-9.]+)", ln)
    if m and m.group(1) in launch:
        launch[m.group(1)]["peak"] = float(m.group(2))
        launch[m.group(1)]["f100"] = float(m.group(3))
toks = [(m, d) for m, d in launch.items() if "peak" in d]
win = [(m, d) for m, d in toks if d["peak"] >= 1.5]
los = [(m, d) for m, d in toks if d["peak"] < 1.3 and d["f100"] <= 0.05]
sample = los + win[:20]
names = {}
with cf.ThreadPoolExecutor(max_workers=12) as ex:
    for (m, d), nm in zip(sample, ex.map(lambda x: get_name(x[0]), sample)):
        names[m] = nm


def low(nm):
    return nm and nm not in ("(too-big)",) and nm == nm.lower() and nm.strip() != ""


lw = [m for m, d in los if low(names.get(m))]
ww = [m for m, d in win[:20] if low(names.get(m))]
print(f"LOSERS lowercase-name: {len(lw)}/{len(los)} ({len(lw)/len(los)*100:.0f}%)")
print(f"WINNERS(sample {min(20,len(win))}) lowercase-name: {len(ww)}/{min(20,len(win))} ({len(ww)/min(20,len(win))*100:.0f}%)")
print("\nLOSER names:")
for m, d in sorted(los, key=lambda x: x[1]["dev"]):
    nm = names.get(m)
    print(f"  dev={d['dev']/1e9:.2f} peak={d['peak']:.2f}  {('LOWER ' if low(nm) else '      ')}{nm!r}")
print("\nWINNER names (sample):")
for m, d in win[:20]:
    nm = names.get(m)
    print(f"  dev={d['dev']/1e9:.2f} peak={d['peak']:.2f}  {('LOWER ' if low(nm) else '      ')}{nm!r}")
