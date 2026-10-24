#!/usr/bin/env python3
# READ-ONLY (public RPC, no keys, nothing sent). Rule 3 "trend" study on OUR real rule #2 buys (PROD wallet 2g7rYv7y...).
# For each token we really bought: every pump.fun trade on its curve from the create to ~S+400 slots (~85 s), in exact
# on-chain order (slot, then the curve's reserves chain). Entry = our REAL buy (real tx, real price, real cost).
# "Sell right after trade N" = our real tokens sold into the curve state right after trade N:
#   SOL out = vSOL * q / (vTok + q)  (pump.fun constant product on virtual reserves), minus the pump fee bps of our real sell,
#   minus our real sell's tx fee, plus the token-account rent our sell gets back. Before our real sell the curve states are
#   the on-chain ones; after it they are replayed WITHOUT our sell (others' buys by SOL, sells by tokens) = "what if we held".
# usage: python3 -I trend5.py <out dir>
import sys, os, json, time, base64, itertools, urllib.request, concurrent.futures as cf, datetime
OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
WALLET = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"
# RPC: the owner's Constant-K endpoint if RPC_URL_FILE is set (URL kept in a private file, never printed), then public mainnet-beta
EPS = ([open(os.environ["RPC_URL_FILE"]).read().strip()] if os.environ.get("RPC_URL_FILE") else []) + ["https://api.mainnet-beta.solana.com"]
GAP = float(os.environ.get("RPC_GAP", "0.28"))        # seconds between requests (0.28 = mainnet-beta's 40 req / 10 s)
HORIZON = 400
import threading
_lk = threading.Lock(); _last = [0.0]


def rpc(m, p):
    """mainnet-beta first (paced to ~3.5 req/s: its limit is 40 req / 10 s per method), publicnode as fallback;
    a null getTransaction counts as a miss on that endpoint"""
    for i in range(8):
        for ep in EPS:
            with _lk:
                w = _last[0] + GAP - time.time()
                if w > 0: time.sleep(w)
                _last[0] = time.time()
            try:
                r = json.load(urllib.request.urlopen(urllib.request.Request(ep, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(),
                                                                             headers={"content-type": "application/json"}), timeout=60))
                if "error" in r: continue
                if r["result"] is None and m == "getTransaction": continue
                return r["result"]
            except Exception:
                continue
        time.sleep(2 + 2 * i)
    raise RuntimeError(f"rpc failed {m}")


B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))


DISC = bytes([189, 219, 127, 211, 78, 230, 97, 238])
def events(tx):
    out = []
    for l in (tx["meta"] or {}).get("logMessages") or []:
        if not l.startswith("Program data: "): continue
        s = l[14:].strip(); s += "=" * (-len(s) % 4)
        try: raw = base64.b64decode(s)
        except Exception: continue
        if raw[:8] != DISC or len(raw) < 225: continue
        u = lambda o: int.from_bytes(raw[o:o + 8], "little")
        out.append(dict(mint=b58(raw[8:40]), sol=u(40), tok=u(48), buy=raw[56] == 1, user=b58(raw[57:89]), ts=u(89), vsol=u(97), vtok=u(105),
                        fee_bps=u(161), fee=u(169), cfee_bps=u(209), cfee=u(217)))
    return out


CACHE = os.path.join(OUT, "txcache"); os.makedirs(CACHE, exist_ok=True)
MISSING = []
def gettx(sig):
    f = os.path.join(CACHE, sig + ".json")
    if os.path.exists(f): return json.load(open(f))
    for attempt in range(3):
        try:
            tx = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
            if tx: json.dump(tx, open(f, "w")); return tx
        except RuntimeError:
            time.sleep(5 * (attempt + 1))
    MISSING.append(sig); return None


def keys(tx):
    k = list(tx["transaction"]["message"]["accountKeys"])
    la = (tx["meta"] or {}).get("loadedAddresses") or {}
    return k + la.get("writable", []) + la.get("readonly", [])


# 1. our wallet's pump trades (last 30 h)
now = time.time()
ws = [s for s in rpc("getSignaturesForAddress", [WALLET, {"limit": 1000}]) if s.get("err") is None and (s.get("blockTime") or 0) > now - 30 * 3600]
print(f"wallet txs (ok, last 30 h): {len(ws)}", flush=True)
ours = {}
with cf.ThreadPoolExecutor(4) as ex:
    for s, tx in zip(ws, ex.map(lambda s: gettx(s["signature"]), ws)):
        if not tx: continue
        k = keys(tx); i = k.index(WALLET) if WALLET in k else None
        chg = (tx["meta"]["postBalances"][i] - tx["meta"]["preBalances"][i]) if i is not None else 0
        rent_new = sum(1 for a, b in zip(tx["meta"]["preBalances"], tx["meta"]["postBalances"]) if a == 0 and b == 2039280)
        for e in events(tx):
            if e["user"] != WALLET: continue
            ours.setdefault(e["mint"], []).append(dict(e, sig=s["signature"], slot=tx["slot"], chg=chg, txfee=tx["meta"]["fee"], rent_new=rent_new, bt=tx.get("blockTime")))
for m in ours: ours[m].sort(key=lambda e: (e["slot"], not e["buy"]))
ours = {m: v for m, v in ours.items() if any(e["buy"] for e in v) and any(not e["buy"] for e in v)}
SKIP = [x for x in os.environ.get("SKIP", "").split(",") if x]          # mint prefixes another worker fetches
ours = {m: v for m, v in ours.items() if not any(m.startswith(x) for x in SKIP)}
print(f"tokens with our buy + sell: {len(ours)}", flush=True)

# 2. every trade on each token's curve, create .. buy slot + HORIZON
res = {}
for mint, mine in ours.items():
    buy = next(e for e in mine if e["buy"]); bs = buy["slot"]
    sigs, before = [], None
    for _ in range(40):
        p = {"limit": 1000}
        if before: p["before"] = before
        r = rpc("getSignaturesForAddress", [mint, p])
        if not r: break
        sigs += r; before = r[-1]["signature"]
        if len(r) < 1000 or r[-1]["slot"] < bs - 5: break
    sigs = [s for s in sigs if s.get("err") is None and bs - 5 <= s["slot"] <= bs + HORIZON]
    with cf.ThreadPoolExecutor(int(os.environ.get("THREADS", "2"))) as ex:
        txs = list(ex.map(lambda s: gettx(s["signature"]), sigs))
    evs = []; create = None
    for s, tx in zip(sigs, txs):
        if not tx: continue
        logs = (tx["meta"] or {}).get("logMessages") or []
        if any("Instruction: Create" in l for l in logs): create = (tx["slot"], s["signature"])
        payer = keys(tx)[0]
        for j, e in enumerate(events(tx)):
            if e["mint"] != mint or (e["sol"] == 0 and e["tok"] == 0): continue
            evs.append(dict(e, sig=s["signature"], slot=tx["slot"], payer=payer, j=j, bt=tx.get("blockTime")))
    # exact order: by slot, then by the reserves chain (each trade's pre-state = previous trade's post-state)
    pre = lambda e: e["vsol"] - e["sol"] if e["buy"] else e["vsol"] + e["sol"]
    by = {}
    for e in evs: by.setdefault(e["slot"], []).append(e)
    order = []; V = None; breaks = 0
    for sl in sorted(by):
        left = sorted(by[sl], key=lambda e: (e["sig"], e["j"]))
        while left:
            nx = [e for e in left if V is not None and abs(pre(e) - V) <= 2]
            if not nx:
                if V is not None: breaks += 1
                nx = sorted(left, key=pre)
            e = nx[0]; order.append(e); left.remove(e); V = e["vsol"]
    res[mint] = dict(mine=mine, create=create, events=order, breaks=breaks, nsigs=len(sigs))
    print(f"{mint}: {len(sigs)} txs, {len(order)} trades in [buy slot-5, buy slot+{HORIZON}], create {create}, chain breaks {breaks}", flush=True)
json.dump(res, open(os.path.join(OUT, "raw.json"), "w"))
print(f"txs that could not be fetched: {len(MISSING)} {MISSING[:5]}")
print("saved raw.json")
