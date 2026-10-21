# READ-ONLY (host, public RPC): on-chain history of every launch creator, for the creator-reputation filters in FILTERS2.md.
# For each creator wallet:   all signatures (newest first, up to MAXP pages of 1000) -> prior tx count / wallet age at each
#                            launch (only signatures with slot < S are used: no look-ahead), plus the create tx's signature
#                            (the creator's signature in slot S).
#                            the oldest signature's transaction (when the history is complete) -> first funder (the other
#                            account whose SOL balance fell the most in the wallet's first tx).
# For each launch:           the creator's pump.fun creator-vault PDA (["creator-vault", creator], pump program) signatures
#                            BEFORE the create tx (before=<create sig>, one page of 1000) = trades on the creator's earlier
#                            pump.fun coins (every pump buy/sell pays the creator fee into that vault) and when the first was.
# Nothing is sent; only getSignaturesForAddress / getTransaction. <= 3 threads, both public endpoints, retries.
# usage: python3 creator_hist.py <out.json> <launches.json> [<launches.json> ...]
import sys, json, time, hashlib, threading, urllib.request, concurrent.futures as cf

OUT = sys.argv[1]
EPS = ["https://solana-rpc.publicnode.com", "https://api.mainnet-beta.solana.com"]
MAXP = 4
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58d(s):
    n = 0
    for c in s: n = n * 58 + B58.index(c)
    b = n.to_bytes(32, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b.lstrip(b"\0") if len(b) != 32 else b


def b58e(b):
    n = int.from_bytes(b, "big"); s = ""
    while n: n, r = divmod(n, 58); s = B58[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s


P = 2 ** 255 - 19; D = -121665 * pow(121666, P - 2, P) % P


def on_curve(b):
    y = int.from_bytes(b, "little") & ((1 << 255) - 1)
    u = (y * y - 1) % P; v = (D * y * y + 1) % P
    x2 = u * pow(v, P - 2, P) % P
    return x2 == 0 or pow(x2, (P - 1) // 2, P) == 1


def pda(seeds, prog):
    pb = b58d(prog)
    for bump in range(255, -1, -1):
        h = hashlib.sha256(b"".join(seeds) + bytes([bump]) + pb + b"ProgramDerivedAddress").digest()
        if not on_curve(h): return b58e(h)


lock = threading.Lock(); ncall = [0]; nerr = [0]


def rpc(method, params):
    for attempt in range(8):
        with lock: ncall[0] += 1
        ep = EPS[0] if attempt < 3 else EPS[attempt % 2]           # publicnode first (mainnet-beta 429s quickly)
        try:
            req = urllib.request.Request(ep, data=json.dumps(dict(jsonrpc="2.0", id=1, method=method, params=params)).encode(),
                                         headers={"content-type": "application/json", "user-agent": "curl/8.5.0"})
            r = json.load(urllib.request.urlopen(req, timeout=30))
            if "result" in r: return r["result"]
            with lock: nerr[0] += 1
        except Exception:
            with lock: nerr[0] += 1
        time.sleep(0.5 * (attempt + 1))
    return "ERR"


def sigs(addr, before=None, pages=MAXP):
    out = []; complete = False
    for _ in range(pages):
        p = dict(limit=1000)
        if before: p["before"] = before
        r = rpc("getSignaturesForAddress", [addr, p])
        if r == "ERR": return out, None
        out += [(x["signature"], x["slot"], x.get("blockTime"), x.get("err") is not None) for x in r]
        if len(r) < 1000: complete = True; break
        before = r[-1]["signature"]
    return out, complete


launch_S = {}
for path in sys.argv[2:]:
    for r in json.load(open(path))["launches"]:
        launch_S.setdefault(r["creator"], set()).add(r["S"])
print(f"creators {len(launch_S)}  launches {sum(len(v) for v in launch_S.values())}", flush=True)
try: res = json.load(open(OUT))
except Exception: res = {}


def one(creator):
    if creator in res and res[creator].get("ok"): return
    wl, complete = sigs(creator)
    rec = dict(ok=wl is not None and complete is not None, complete=complete, n=len(wl),
               sigs=[[s[1], s[2], int(s[3])] for s in wl])      # (slot, blockTime, failed) newest first
    # first funder (only when the whole history was listed)
    if complete and wl:
        sig0 = wl[-1][0]
        tx = rpc("getTransaction", [sig0, dict(encoding="json", maxSupportedTransactionVersion=0)])
        if tx not in ("ERR", None):
            keys = tx["transaction"]["message"]["accountKeys"] + tx["meta"].get("loadedAddresses", {}).get("writable", []) + tx["meta"].get("loadedAddresses", {}).get("readonly", [])
            pre, post = tx["meta"]["preBalances"], tx["meta"]["postBalances"]
            deltas = [(post[i] - pre[i], keys[i]) for i in range(min(len(keys), len(pre)))]
            got = [d for d, k in deltas if k == creator]
            out = sorted((d, k) for d, k in deltas if k != creator)
            rec["first"] = dict(slot=wl[-1][1], bt=wl[-1][2], payer=keys[0], funder=out[0][1] if out and out[0][0] < 0 else None,
                                funded_lam=got[0] if got else None)
    # per launch: create sig + creator-vault history before it
    vault = pda([b"creator-vault", b58d(creator)], PUMP)
    rec["vault"] = vault; rec["launch"] = {}
    for S in sorted(launch_S[creator]):
        at = [s for s in wl if s[1] == S]
        csig = at[-1][0] if at else None                      # the oldest of the creator's signatures in slot S = the create
        lr = dict(create_sig=bool(csig))
        if csig:
            vl, vc = sigs(vault, before=csig, pages=1)
            if vl is not None:
                vl = [v for v in vl if v[1] < S]
                lr.update(vn=len(vl), vcomplete=vc, vfirst_bt=vl[-1][2] if vl else None, vlast_bt=vl[0][2] if vl else None,
                          vbt=[v[2] for v in vl][:1000])
        rec["launch"][str(S)] = lr
    with lock: res[creator] = rec


todo = [c for c in launch_S if not (c in res and res[c].get("ok"))]
t0 = time.time()
with cf.ThreadPoolExecutor(3) as ex:
    futs = [ex.submit(one, c) for c in todo]
    for i, f in enumerate(cf.as_completed(futs)):
        f.result()
        if i % 25 == 24:
            with lock: json.dump(res, open(OUT, "w"))
            print(f"{i + 1}/{len(todo)}  calls {ncall[0]}  errors {nerr[0]}  {time.time() - t0:.0f}s", flush=True)
json.dump(res, open(OUT, "w"))
print(f"done {len(res)} creators, calls {ncall[0]}, {time.time() - t0:.0f}s", flush=True)
