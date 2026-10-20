# READ-ONLY (host; public RPCs + Jito's public bundle API): every trade of the mint inside the create slot S, with its
# Jito bundle (bundles.jito.wtf), so the creator's OWN extra bundles are not mistaken for snipers. A row is CREATOR-side
# when it is the create / glued bundle, or sits in a Jito bundle that shares a signer, fee payer or tipper with the
# creator side (expanded until stable); PROBABLE-creator when it sits in a bundle with >= 2 buys of the mint by
# different wallets; else SNIPER. Position = txs after the creator's glued bundle (same block).
# usage: python3 bundlestudy.py <out.json> [--rec-all <record_window dir>] [mint:slot ...]
#        RPC_URLS=comma list (default publicnode + mainnet-beta, round-robin), THREADS=3
import sys, os, re, json, time, glob, base64, threading, itertools, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
EPS = os.environ.get("RPC_URLS", "https://solana-rpc.publicnode.com,https://api.mainnet-beta.solana.com").split(",")
_rr = itertools.cycle(range(len(EPS))); _lock = threading.Lock()
VOTE = "Vote111111111111111111111111111111111111111"
SYS = "11111111111111111111111111111111"
TRADE_DISC = bytes([189, 219, 127, 211, 78, 230, 97, 238])
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
B58I = {c: i for i, c in enumerate(B58)}
TIPS = json.load(open(os.environ["TIPMAP_JSON"])) if os.environ.get("TIPMAP_JSON") else None
if TIPS is None:
    import importlib.util
    spec = importlib.util.spec_from_file_location("tipsize_map", os.path.join(HERE, "tipsize.py"))
    src = open(os.path.join(HERE, "tipsize.py")).read()
    ns = {"__file__": os.path.join(HERE, "tipsize.py"), "__name__": "tipsize_map"}
    exec(compile(src.split("\nTIPS =")[0], "tipsize.py", "exec"), ns)   # only the imports + tipmap() definition
    TIPS = ns["tipmap"]()


def label(dst):
    if dst in TIPS: return TIPS[dst]
    if dst.startswith(("noz", "TEMPa")): return "nozomi"
    if dst.lower().startswith("astra"): return "astralane"
    return None


def http_json(url, data=None, timeout=90):
    req = urllib.request.Request(url, data=data, headers={"content-type": "application/json", "user-agent": "sniper-study"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def rpc(meth, params, tries=10):
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": meth, "params": params}).encode()
    for i in range(tries):
        with _lock: ep = EPS[next(_rr)]
        try:
            r = http_json(ep, data)
            if "error" in r:
                if r["error"].get("code") in (-32007, -32009): return None
                time.sleep(1 + i); continue
            return r.get("result")
        except Exception:
            time.sleep(1 + i)
    return None


_jlock = threading.Lock(); _jlast = [0.0]
JITO_GAP = float(os.environ.get("JITO_GAP", "0.2"))   # seconds between Jito API calls (all threads)


def jito(path, tries=6):
    for i in range(tries):
        with _jlock:
            w = _jlast[0] + JITO_GAP - time.time()
            if w > 0: time.sleep(w)
            _jlast[0] = time.time()
        try:
            return http_json("https://bundles.jito.wtf/api/v1/bundles/" + path, timeout=20)
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            time.sleep(2 * (i + 1))
        except Exception:
            time.sleep(2 * (i + 1))
    return "ERR"


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
        sol = int.from_bytes(raw[o:o + 8], "little"); o += 16
        buy = raw[o]; o += 1
        out.append(dict(mint=mint, sol=sol, buy=buy, user=b58enc(raw[o:o + 32])))
    return out


def txmeta(t):
    msg = t["transaction"]["message"]; meta = t.get("meta") or {}
    la = meta.get("loadedAddresses") or {}
    keys = list(msg["accountKeys"]) + la.get("writable", []) + la.get("readonly", [])
    nsig = msg["header"]["numRequiredSignatures"]
    tips = []
    for ix in list(msg["instructions"]) + [ix for inn in (meta.get("innerInstructions") or []) for ix in inn.get("instructions") or []]:
        try:
            if keys[ix["programIdIndex"]] != SYS: continue
            raw = b58dec(ix["data"])
        except Exception:
            continue
        if len(raw) >= 12 and int.from_bytes(raw[:4], "little") == 2 and len(ix.get("accounts") or []) >= 2:
            lab = label(keys[ix["accounts"][1]])
            if lab: tips.append([lab, int.from_bytes(raw[4:12], "little") / 1e9])
    return dict(sig=t["transaction"]["signatures"][0], payer=keys[0], signers=keys[:nsig], prio=((meta.get("fee") or 0) - 5000 * nsig) / 1e9, tips=tips)


def one(item):
    m, S, lc = item
    b = rpc("getBlock", [S, {"encoding": "json", "maxSupportedTransactionVersion": 1, "transactionDetails": "full", "rewards": False}])
    if not b: print(f"{m[:8]} S={S}: block unavailable", flush=True); return None
    txs = [t for t in b["transactions"] if VOTE not in t["transaction"]["message"]["accountKeys"]]
    rows = []
    for i, t in enumerate(txs):
        meta = t.get("meta") or {}
        tr = [e for e in trades(meta.get("logMessages")) if e["mint"] == m]
        if not tr: continue
        rows.append(dict(idx=i, ok=meta.get("err") is None, buy=bool(tr[0]["buy"]), sol=sum(e["sol"] for e in tr) / 1e9,
                         users=sorted({e["user"] for e in tr}), **txmeta(t)))
    del b, txs
    okr = [r for r in rows if r["ok"]]
    if not okr: return None
    ci = okr[0]["idx"]; ge = ci
    for r in okr[1:]:
        if r["idx"] == ge + 1 and r["buy"]: ge = r["idx"]
        else: break
    for r in rows:
        r["pos"] = r["idx"] - ge
        r["cls"] = "create" if r["idx"] == ci else ("glued" if ci < r["idx"] <= ge and r["ok"] else None)
    # Jito bundle of every row; then each bundle's details
    for r in rows:
        j = jito("transaction/" + r["sig"])
        r["bundle"] = j[0]["bundle_id"] if isinstance(j, list) and j else (None if j != "ERR" else "ERR")
    bundles = {}
    for bid in {r["bundle"] for r in rows if r["bundle"] and r["bundle"] != "ERR"}:
        d = jito("bundle/" + bid)
        if isinstance(d, list) and d:
            d = d[0]; bundles[bid] = dict(tippers=d.get("tippers") or [], tip=(d.get("landedTipLamports") or 0) / 1e9, sigs=d.get("txSignatures") or [],
                                          validator=d.get("validator"))
    # creator side: create + glued, then expand through shared bundles / signers / payers / tippers
    C = set()
    for r in rows:
        if r["cls"]: C |= set(r["signers"]) | set(r["users"]) | {r["payer"]}
    cb = {r["bundle"] for r in rows if r["cls"] and r["bundle"] in bundles}
    changed = True
    while changed:
        changed = False
        for r in rows:
            if r["cls"]: continue
            bid = r["bundle"]; bd = bundles.get(bid)
            linked = (bid in cb) or (set(r["signers"]) | {r["payer"]} | set(r["users"])) & C
            if bd and not linked:
                mates = [x for x in rows if x["bundle"] == bid]
                linked = bool(set(bd["tippers"]) & C) or any((set(x["signers"]) | {x["payer"]}) & C for x in mates)
            if linked:
                r["cls"] = "creator-bundle"; C |= set(r["signers"]) | set(r["users"]) | {r["payer"]}
                if bid in bundles: cb.add(bid)
                changed = True
    for r in rows:
        if r["cls"]: continue
        bid = r["bundle"]
        mates = [x for x in rows if bid and bid != "ERR" and x["bundle"] == bid and x["buy"]]
        r["cls"] = "probable-creator" if len({u for x in mates for u in x["users"]}) >= 2 else "sniper"
        bd = bundles.get(bid)
        r["bundle_tip"] = bd["tip"] if bd else None
        r["bundle_size"] = len(bd["sigs"]) if bd else None
    out = dict(mint=m, S=S, leader_client=lc, cidx=ci, glued_end=ge, rows=rows,
               validator=next((bd["validator"] for bd in bundles.values() if bd.get("validator")), None))
    sn = [r for r in rows if r["cls"] == "sniper" and r["ok"] and r["buy"]]
    crb = [r for r in rows if r["cls"] in ("creator-bundle", "probable-creator") and r["ok"] and r["buy"]]
    f = sn[0] if sn else None
    print(f"{m[:8]} S={S} {lc or '':18} creator extra buys {len(crb):2} (first +{crb[0]['pos'] if crb else '-'})  snipers {len(sn):2}  "
          + (f"first sniper +{f['pos']} {f['sol']:.2f} SOL {f['users'][0][:6]} prio {f['prio']:.4f} tips {f['tips']} bundle {'yes tip %.4f' % f['bundle_tip'] if f['bundle_tip'] is not None else 'no'}" if f else "no sniper"), flush=True)
    return out


OUT = sys.argv[1]; args = sys.argv[2:]; items = []
if args and args[0] == "--rec-all":
    for fn in sorted(glob.glob(os.path.join(args[1], "*.json"))):
        if fn.endswith("_index.json"): continue
        r = json.load(open(fn)); items.append((r["mint"], r["S"], r.get("leader_client")))
    args = args[2:]
items += [(a.split(":")[0], int(a.split(":")[1]), None) for a in args]
with ThreadPoolExecutor(int(os.environ.get("THREADS", "3"))) as ex:
    res = [r for r in ex.map(one, items) if r]
json.dump(res, open(OUT, "w"))
print(f"done: {len(res)} of {len(items)} launches -> {OUT}", flush=True)
