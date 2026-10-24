#!/usr/bin/env python3
# READ-ONLY, RESUMABLE ledger fetch: every raw transaction is cached to disk as it arrives (txc_<wallet>/<sig>.json), so a
# stop or crash loses nothing. Owner's RPC first (parallel), then public mainnet-beta paced to ~3.5 req/s for older history.
# usage: RPC_URL=... python3 -I fill2.py <wallet> <out.json>
import sys, os, json, time, threading, urllib.request, concurrent.futures as cf
W, OUT = sys.argv[1], sys.argv[2]; EP = os.environ["RPC_URL"]; PUB = "https://api.mainnet-beta.solana.com"
HERE = os.path.dirname(os.path.abspath(__file__)); C = os.path.join(HERE, f"txc_{W[:6]}"); os.makedirs(C, exist_ok=True)
def post(ep, m, p, timeout=60):
    return json.load(urllib.request.urlopen(urllib.request.Request(ep, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=timeout))
cache = OUT + ".sigs"
if os.path.exists(cache): sigs = json.load(open(cache))
else:
    sigs, before = [], None
    while True:
        p = {"limit": 1000}
        if before: p["before"] = before
        r = post(PUB, "getSignaturesForAddress", [W, p]).get("result")
        if not r: break
        sigs += r; before = r[-1]["signature"]; time.sleep(0.5)
        if len(r) < 1000: break
    json.dump(sigs, open(cache, "w"))
have = lambda s: os.path.exists(os.path.join(C, s + ".json"))
todo = [s["signature"] for s in sigs if not have(s["signature"])]
print(f"{W[:8]}: {len(sigs)} sigs, cached {len(sigs) - len(todo)}, to fetch {len(todo)}", flush=True)
def fast(sig):
    for i in range(3):
        try:
            r = post(EP, "getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}]).get("result")
            if r: json.dump(r, open(os.path.join(C, sig + ".json"), "w")); return True
            return False
        except Exception: time.sleep(1 + i)
    return False
with cf.ThreadPoolExecutor(10) as ex: ok = sum(ex.map(fast, todo))
todo = [s for s in todo if not have(s)]
print(f"   owner RPC gave {ok}; public path for {len(todo)}", flush=True)
lock = threading.Lock(); last = [0.0]; done = [0]
def slow(sig):
    for i in range(8):
        with lock:
            w = last[0] + 0.29 - time.time()
            if w > 0: time.sleep(w)
            last[0] = time.time()
        try:
            r = post(PUB, "getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}])
            if r.get("result"): json.dump(r["result"], open(os.path.join(C, sig + ".json"), "w")); break
        except Exception: time.sleep(2 + 2 * i)
    with lock:
        done[0] += 1
        if done[0] % 250 == 0: print(f"   public path: {done[0]} / {len(todo)}", flush=True)
with cf.ThreadPoolExecutor(4) as ex: list(ex.map(slow, todo))
# parse every cached tx with ledger.py's per-tx logic
src = open(os.path.join(HERE, "ledger.py")).read(); g = {"__name__": "x"}
exec(src[:src.index("sigs, before = [], None")].replace("W, OUT = sys.argv[1], sys.argv[2]; ", "").replace('EP = os.environ["RPC_URL"]; ', ""), g)
exec(src[src.index("def one(s):"):src.index("with cf.ThreadPoolExecutor(10) as ex: L =")], g); g["W"] = W
L = []
for s in sigs:
    f = os.path.join(C, s["signature"] + ".json")
    if not os.path.exists(f): L.append(dict(sig=s["signature"], slot=s["slot"], bt=s.get("blockTime"), missing=True)); continue
    tx = json.load(open(f)); g["rpc"] = lambda m, p, ep=None, tries=8, _t=tx: _t
    L.append(g["one"](s))
bal = post(EP, "getBalance", [W])["result"]["value"] / 1e9; hold = []
for prog in ("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"):
    r = post(EP, "getTokenAccountsByOwner", [W, {"programId": prog}, {"encoding": "jsonParsed"}])["result"]
    hold += [(a["account"]["data"]["parsed"]["info"]["mint"], a["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"]) for a in r["value"]]
json.dump(dict(wallet=W, balance_now=bal, holdings_now=[h for h in hold if h[1]], txs=L), open(OUT, "w"))
print(f"   saved {len(L)} txs, missing {sum(1 for x in L if x.get('missing'))}; balance {bal:.4f}", flush=True)
