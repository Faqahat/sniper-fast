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
    for i in range(5):
        try:
            return json.load(urllib.request.urlopen(req, timeout=20)).get("result")
        except Exception:
            time.sleep(0.3 * (i + 1))
    return None


def get_name(mint):
    # oldest sig = create; cap pagination at 3 pages
    sgs = []
    before = None
    pages = 0
    while pages < 4:
        prm = [mint, {"limit": 1000}] if before is None else [mint, {"limit": 1000, "before": before}]
        r = rpc("getSignaturesForAddress", prm)
        if not r:
            break
        sgs += r
        pages += 1
        if len(r) < 1000:
            break
        before = r[-1]["signature"]
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
                p = 8
                ln = int.from_bytes(raw[p:p + 4], "little")
                return raw[p + 4:p + 4 + ln].decode("utf-8", "replace")
    return None


# parse log
launch = {}
for ln in open("/root/sniper-fast/paper_blacklist.log"):
    m = re.search(r"PAPER launch #\d+ slot=\d+ mint=(\w+) dev_buy=(\d+)", ln)
    if m and m.group(1) not in launch:
        launch[m.group(1)] = {"dev": int(m.group(2))}
    m = re.search(r"PAPER done mint=(\w+).*peak_r=([0-9.]+).*@1.00=([+-][0-9.]+)", ln)
    if m and m.group(1) in launch:
        d = launch[m.group(1)]
        d["peak"] = float(m.group(2))
        d["f100"] = float(m.group(3))

toks = [(mint, d) for mint, d in launch.items() if "peak" in d]
win = [(m, d) for m, d in toks if d["peak"] >= 1.5]
los = [(m, d) for m, d in toks if d["peak"] < 1.3 and d["f100"] <= 0.05]


def is_round(dev_lam):
    sol = dev_lam / 1e9
    return abs(sol - round(sol)) < 0.03 and sol >= 1.0


# fetch names for all labeled
allt = win + los
names = {}
with cf.ThreadPoolExecutor(max_workers=10) as ex:
    for (m, d), nm in zip(allt, ex.map(lambda x: get_name(x[0]), allt)):
        names[m] = nm or "?"


def analyze(group, label):
    n = len(group)
    rnd = sum(1 for m, d in group if is_round(d["dev"]))
    low = sum(1 for m, d in group if names[m] != "?" and names[m] == names[m].lower() and names[m].strip())
    either = sum(1 for m, d in group if is_round(d["dev"]) or (names[m] != "?" and names[m] == names[m].lower() and names[m].strip()))
    print(f"{label}: n={n}  round-dev={rnd}({rnd/n*100:.0f}%)  lowercase-name={low}({low/n*100:.0f}%)  EITHER={either}({either/n*100:.0f}%)")


print(f"=== BLACKLIST paper: {len(win)} winners vs {len(los)} losers ===")
analyze(win, "WINNERS")
analyze(los, "LOSERS ")
print("\nLOSERS detail (dev, round?, name):")
for m, d in sorted(los, key=lambda x: x[1]["dev"]):
    r = "ROUND" if is_round(d["dev"]) else ""
    nm = names[m]
    low = "lower" if (nm != "?" and nm == nm.lower() and nm.strip()) else ""
    print(f"  dev={d['dev']/1e9:.3f} peak={d['peak']:.2f} {r:5} {low:5} {nm!r}")
