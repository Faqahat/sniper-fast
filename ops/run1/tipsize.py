# READ-ONLY, self-contained (host; RPC from $RPC_URL, default public mainnet): for each launch, every outside buy of the
# mint inside the create slot S after the creator's glued bundle, with its position, size, wallet, priority fee and the
# tips it paid (system transfers to known sender tip accounts: src/send/mod.rs + data/sender-tip-accounts.json).
# Answers: on the launches worth having, who landed first and what did they pay to be there?
# usage: python3 tipsize.py <out.json> <mint:slot> [<mint:slot> ...]   (or --rec <record_window dir> for its fired launches,
#        --rec-all <dir> for every recorded launch; THREADS=2 parallel block fetches)
#        python3 tipsize.py --dump-tipmap tipmap.json, then TIPMAP_JSON=tipmap.json on a host without the repo
import sys, os, re, json, time, glob, base64, urllib.request

RPC = os.environ.get("RPC_URL", "https://api.mainnet-beta.solana.com")
ROOT = os.path.dirname(os.path.abspath(__file__)) + "/../.."
VOTE = "Vote111111111111111111111111111111111111111"
SYS = "11111111111111111111111111111111"
TRADE_DISC = bytes([189, 219, 127, 211, 78, 230, 97, 238])
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
B58I = {c: i for i, c in enumerate(B58)}


def tipmap():
    m = {}
    src = open(os.path.join(ROOT, "src/send/mod.rs")).read()
    i = src.find("pub fn known_tip_accounts"); body = src[i:i + 60000]; j = body.find("\n}\n"); body = body[:j] if j > 0 else body
    cur = None
    for line in body.splitlines():
        km = re.findall(r"SendKind::(\w+)", line)
        if km and "=>" in line: cur = km[0].lower()
        for a in re.findall(r'"([1-9A-HJ-NP-Za-km-z]{32,44})"', line):
            if cur: m.setdefault(a, cur)
    for k, v in json.load(open(os.path.join(ROOT, "data/sender-tip-accounts.json"))).items():
        if isinstance(v, dict) and isinstance(v.get("tip_accounts"), list):
            for a in v["tip_accounts"]:
                if isinstance(a, str): m.setdefault(a, k)
    norm = {"jitobundle": "jito", "jitotx": "jito", "quicknode_lil_jit": "jito", "jito_bam": "jito", "iris": "astralane", "astralane_iris": "astralane",
            "temporal_nozomi": "nozomi", "helius_sender": "helius", "hellomoon_lunar_lander": "lunar", "zeroslot": "0slot", "bloxroute_trader_api": "bloxroute",
            "bloxroute_legacy": "bloxroute", "falcon_corvus": "falcon", "nodeone": "node1"}
    return {a: norm.get(n, n) for a, n in m.items()}


TIPS = json.load(open(os.environ["TIPMAP_JSON"])) if os.environ.get("TIPMAP_JSON") else tipmap()
if len(sys.argv) > 1 and sys.argv[1] == "--dump-tipmap":
    json.dump(TIPS, open(sys.argv[2], "w")); print(f"{len(TIPS)} tip accounts -> {sys.argv[2]}"); sys.exit(0)


def label(dst):
    if dst in TIPS: return TIPS[dst]
    if dst.startswith(("noz", "TEMPa")): return "nozomi"
    if dst.lower().startswith("astra"): return "astralane"
    return None


def rpc(meth, params, tries=8):
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": meth, "params": params}).encode()
    for i in range(tries):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(RPC, data=data, headers={"content-type": "application/json"}), timeout=90))
            if "error" in r:
                if r["error"].get("code") in (-32007, -32009): return None
                time.sleep(2 * (i + 1)); continue
            return r.get("result")
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def b58enc(b):
    n = int.from_bytes(b, "big"); out = []
    while n:
        n, r = divmod(n, 58); out.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\x00"))) + "".join(reversed(out))


def b58dec(s):
    n = 0
    for c in s: n = n * 58 + B58I[c]
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\x00" * (len(s) - len(s.lstrip("1"))) + b


def trades(logs):
    out = []
    for l in logs or []:
        if not l.startswith("Program data: "): continue
        try: raw = base64.b64decode(l[14:] + "===")
        except Exception: continue
        if raw[:8] != TRADE_DISC or len(raw) < 129: continue
        o = 8; mint = b58enc(raw[o:o + 32]); o += 32
        sol = int.from_bytes(raw[o:o + 8], "little"); o += 8 + 8
        buy = raw[o]; o += 1
        user = b58enc(raw[o:o + 32])
        out.append(dict(mint=mint, sol=sol, buy=buy, user=user))
    return out


def paid(t):
    """(priority fee, [(tip label, lamports)]) of a json-encoded tx; tips = system transfers to known tip accounts, top-level and inner."""
    msg = t["transaction"]["message"]; meta = t.get("meta") or {}
    la = meta.get("loadedAddresses") or {}
    keys = list(msg["accountKeys"]) + la.get("writable", []) + la.get("readonly", [])
    nsig = msg["header"]["numRequiredSignatures"]
    tips = []
    ixs = list(msg["instructions"]) + [ix for inn in (meta.get("innerInstructions") or []) for ix in inn.get("instructions") or []]
    for ix in ixs:
        try:
            if keys[ix["programIdIndex"]] != SYS: continue
            raw = b58dec(ix["data"])
        except Exception:
            continue
        if len(raw) >= 12 and int.from_bytes(raw[:4], "little") == 2 and len(ix.get("accounts") or []) >= 2:
            dst = keys[ix["accounts"][1]]; lab = label(dst)
            if lab: tips.append((lab, int.from_bytes(raw[4:12], "little")))
    return (meta.get("fee") or 0) - 5000 * nsig, tips


OUT = sys.argv[1]
items = []
if sys.argv[2] in ("--rec", "--rec-all"):
    for f in sorted(glob.glob(os.path.join(sys.argv[3], "*.json"))):
        if f.endswith("_index.json"): continue
        r = json.load(open(f))
        if r.get("fired") or sys.argv[2] == "--rec-all": items.append((r["mint"], r["S"], r.get("leader_client")))
    items += [(a.split(":")[0], int(a.split(":")[1]), None) for a in sys.argv[4:]]
else:
    items = [(a.split(":")[0], int(a.split(":")[1]), None) for a in sys.argv[2:]]

def one(item):
    m, S, lc = item
    b = rpc("getBlock", [S, {"encoding": "json", "maxSupportedTransactionVersion": 1, "transactionDetails": "full", "rewards": False}])
    if not b:
        print(f"{m[:8]} S={S}: block unavailable", flush=True); return None
    txs = [t for t in b["transactions"] if VOTE not in t["transaction"]["message"]["accountKeys"]]
    rows = []; ci = ge = None
    for i, t in enumerate(txs):
        meta = t.get("meta") or {}
        tr = [e for e in trades(meta.get("logMessages")) if e["mint"] == m]
        if not tr: continue
        okk = meta.get("err") is None
        if ci is None:
            if okk: ci = ge = i
            continue
        if okk and ge == i - 1 and tr[0]["buy"] and not rows: ge = i; continue      # glued bundle
        prio, tips = paid(t)
        rows.append(dict(idx=i, pos=i - ge, ok=okk, buy=bool(tr[0]["buy"]), sol=sum(e["sol"] for e in tr) / 1e9, wallet=tr[0]["user"],
                         prio=prio / 1e9, tips=[(l, v / 1e9) for l, v in tips]))
    del b
    out = dict(mint=m, S=S, leader_client=lc, n_txs=len(txs), cidx=ci, glued_end=ge, rows=rows)
    first = next((r for r in rows if r["ok"] and r["buy"]), None)
    desc = "-" if not first else f"first outside buy +{first['pos']} {first['sol']:.2f} SOL {first['wallet'][:6]} prio {first['prio']:.4f} tips {first['tips']}"
    print(f"{m[:8]} S={S} {lc or '':10} buys in S after bundle: {sum(1 for r in rows if r['ok'] and r['buy'])}   {desc}", flush=True)
    return out


from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(int(os.environ.get("THREADS", "2"))) as ex:
    res = [r for r in ex.map(one, items) if r]
json.dump(res, open(OUT, "w"))
print(f"done: {len(res)} of {len(items)} launches", flush=True)
