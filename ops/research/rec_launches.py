# READ-ONLY (host; public RPCs, getBlock only): record every launch in parse_logs.py's output for the landing replay:
# blocks S..S+K (exact in-block order), every successful trade of the mint with its block position, the creator's
# glued bundle (consecutive successful buys of the mint right after the create tx, votes not counted; a failed tx or any
# other tx ends the run), the bundle's legs / wallets / SOL, and the create tx's largest top-level SOL transfer to a
# non-signer (the "tip": Lunar moon..., Jito, ...). Output = record_window.py / mini_record.py format (sim_land.py's run()).
# Launches already recorded in a record_window.py dir (--reuse) are copied, not fetched.
# usage: python3 rec_launches.py <launches.json> <out rec dir> <block cache dir> [--reuse dir]   env: K=2 THREADS=3
import sys, os, json, time, base64, threading, urllib.request, glob
from concurrent.futures import ThreadPoolExecutor

LJ, OUT, BLK = sys.argv[1], sys.argv[2], sys.argv[3]
REUSE = sys.argv[sys.argv.index("--reuse") + 1] if "--reuse" in sys.argv else None
K = int(os.environ.get("K", "2"))
os.makedirs(OUT, exist_ok=True); os.makedirs(BLK, exist_ok=True)
EPS = ["https://solana-rpc.publicnode.com", "https://api.mainnet-beta.solana.com"]
cool = {e: 0.0 for e in EPS}; lock = threading.Lock()
VOTE = "Vote111111111111111111111111111111111111111"
SYS = "11111111111111111111111111111111"
TRADE_DISC = bytes([189, 219, 127, 211, 78, 230, 97, 238])
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
B58I = {c: i for i, c in enumerate(B58)}

L = json.load(open(LJ))["launches"]
MINTS = {r["mint"] for r in L}


def b58enc(b):
    n = int.from_bytes(b, "big"); out = []
    while n:
        n, r = divmod(n, 58); out.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\x00"))) + "".join(reversed(out))


def b58dec(s):
    n = 0
    for c in s: n = n * 58 + B58I[c]
    full = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\x00" * (len(s) - len(s.lstrip("1"))) + full


def get_block(s):
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getBlock", "params": [s, {"encoding": "json", "maxSupportedTransactionVersion": 1,
                       "transactionDetails": "full", "rewards": False}]}).encode()
    for i in range(14):
        with lock:
            ep = min(EPS, key=lambda e: cool[e]); wait = cool[ep] - time.time()
        if wait > 0: time.sleep(min(wait, 5))
        try:
            req = urllib.request.Request(ep, data=data, headers={"content-type": "application/json", "user-agent": "curl/8.5.0"})
            r = json.load(urllib.request.urlopen(req, timeout=90))
            if "error" in r:
                if r["error"].get("code") in (-32007, -32009): return None      # skipped / missing slot
                with lock: cool[ep] = time.time() + 2 + i
                continue
            return r["result"]
        except Exception as e:
            with lock: cool[ep] = time.time() + (6 if "429" in str(e) else 2) + i
    return "ERR"


def trades_of(logs):
    out = []
    for l in logs or []:
        if not l.startswith("Program data: "): continue
        try: raw = base64.b64decode(l[14:] + "===")
        except Exception: continue
        if raw[:8] != TRADE_DISC or len(raw) < 129: continue
        mint = b58enc(raw[8:40])
        if mint not in MINTS: continue
        g = lambda a, b: int.from_bytes(raw[a:b], "little")
        e = dict(mint=mint, sol=g(40, 48), tok=g(48, 56), buy=raw[56], user=b58enc(raw[57:89]), vsol=g(97, 105), vtok=g(105, 113), fbps=None, cbps=None)
        if len(raw) >= 225: e.update(fbps=g(161, 169), cbps=g(209, 217))
        out.append(e)
    return out


def largest_transfer(t):
    msg = t["transaction"]["message"]; la = (t.get("meta") or {}).get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    nsig = msg["header"]["numRequiredSignatures"]
    best = (0, None); moon = False; tips = []
    for ix in msg["instructions"]:
        if keys[ix["programIdIndex"]] != SYS: continue
        d = b58dec(ix["data"])
        if len(d) >= 12 and int.from_bytes(d[:4], "little") == 2 and len(ix["accounts"]) >= 2:
            if ix["accounts"][1] < nsig: continue
            dst = keys[ix["accounts"][1]]; lam = int.from_bytes(d[4:12], "little")
            moon |= dst.startswith("moon"); tips.append((lam, dst))
            if lam > best[0]: best = (lam, dst)
    return best, moon, keys[:nsig], tips


def compact(s, x):
    rows = []; n = 0
    for t in x["transactions"]:
        if VOTE in t["transaction"]["message"]["accountKeys"]: continue
        meta = t.get("meta") or {}
        i = n; n += 1
        tr = trades_of(meta.get("logMessages"))
        if not tr: continue
        row = dict(idx=i, ok=meta.get("err") is None, payer=t["transaction"]["message"]["accountKeys"][0], trades=tr)
        (lam, dst), moon, signers, tips = largest_transfer(t)
        row.update(largest=[lam, dst], any_moon=moon, signers=signers, tips=tips, cu_fee=meta.get("fee"))
        rows.append(row)
    return dict(slot=s, blockTime=x.get("blockTime"), n_txs=n, rows=rows)


BC = {}; bl = threading.Lock()


def blk(s):
    with bl:
        if s in BC: return BC[s]
    p = os.path.join(BLK, f"{s}.json")
    if os.path.exists(p):
        b = json.load(open(p))
    else:
        x = get_block(s)
        if x == "ERR": return "ERR"
        b = compact(s, x) if x else dict(slot=s, skipped=True, rows=[], n_txs=0, blockTime=None)
        x = None
        json.dump(b, open(p + ".tmp", "w")); os.replace(p + ".tmp", p)
    with bl: BC[s] = b
    return b


def record(r):
    mint, S = r["mint"], r["S"]
    path = os.path.join(OUT, f"{mint}.json")
    if os.path.exists(path): return "cached"
    if REUSE and os.path.exists(os.path.join(REUSE, f"{mint}.json")):
        x = json.load(open(os.path.join(REUSE, f"{mint}.json")))
        if x["S"] == S and x.get("exact_order_slots", 0) >= K:
            x["src"] = "reuse"; json.dump(x, open(path, "w")); return "reused"
    bs = {}
    for s in range(S, S + K + 1):
        b = blk(s)
        if b == "ERR": return f"ERR block {s}"
        bs[s] = b
    if bs[S].get("skipped"): return "create slot skipped?"
    rows = bs[S]["rows"]
    k = next((n for n, w in enumerate(rows) if any(e["mint"] == mint for e in w["trades"]) and w["ok"]), None)
    if k is None: return "create not found"
    c = rows[k]
    dev = sum(e["sol"] for e in c["trades"] if e["mint"] == mint and e["buy"]) / 1e9
    gl, glegs, gsol, wallets, nxt = 0, 0, 0, set(), c["idx"] + 1
    members = set(c["signers"])
    for w in rows[k + 1:]:
        if w["idx"] != nxt: break
        ev = [e for e in w["trades"] if e["mint"] == mint and e["buy"]]
        if not ev or not w["ok"] or any(e["mint"] == mint and not e["buy"] for e in w["trades"]): break
        gl += 1; glegs += len(ev); gsol += sum(e["sol"] for e in ev); wallets |= {e["user"] for e in ev}; members |= {e["user"] for e in ev} | {w["payer"]}
        nxt += 1
    trades = []
    for s in range(S, S + K + 1):
        for w in bs[s]["rows"]:
            if not w["ok"] or (s == S and w["idx"] < c["idx"]): continue
            for e in w["trades"]:
                if e["mint"] == mint:
                    e = dict(e); e.update(slot=s, idx=w["idx"], payer=w["payer"]); trades.append(e)
    lam, dst = c["largest"]
    creator_set = set(c["signers"])
    rec = dict(mint=mint, S=S, slot_ms=r.get("slot_ms", 217.0), fired=bool(r.get("fire")), engine=r["log"], create_ms=r.get("create_ms"),
               cidx=c["idx"], n_txs=bs[S]["n_txs"], glued_end=nxt, glued=gl, glued_legs=glegs, gsol=gsol / 1e9, bundle_wallets=len(wallets),
               bundle_wallets_new=len(wallets - creator_set), dev=dev, bundle_members=sorted(members), largest_to=dst or "", largest_lam=lam,
               largest_moon=bool(dst and dst.startswith("moon")), any_moon=c["any_moon"], create_tips=c["tips"], create_fee=c.get("cu_fee"),
               creator=r.get("creator"), block_time=bs[S]["blockTime"], trades=trades, window_slots=K, exact_order_slots=K, src="getBlock")
    json.dump(rec, open(path, "w"))
    return f"ok gl={gl} gsol={gsol / 1e9:.2f} trades={len(trades)}"


todo = [r for r in L if not os.path.exists(os.path.join(OUT, f"{r['mint']}.json"))]
print(f"launches {len(L)}, to record {len(todo)}", flush=True)
t0 = time.time(); n = 0; errs = 0
with ThreadPoolExecutor(int(os.environ.get("THREADS", "3"))) as ex:
    for r, res in zip(todo, ex.map(record, todo)):
        n += 1; errs += res.startswith("ERR") or "not found" in res
        if n % 20 == 0 or res.startswith("ERR"):
            print(f"  [{n}/{len(todo)} {time.time() - t0:.0f}s errs {errs}] {r['log']} {r['mint'][:8]} S={r['S']}: {res}", flush=True)
print(f"DONE {n} in {time.time() - t0:.0f}s, errors {errs}", flush=True)
