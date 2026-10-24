#!/usr/bin/env python3
# READ-ONLY: complete a wallet ledger. Signatures cached; transactions from the owner's RPC first (parallel), then the ones it
# does not have (older history) from public mainnet-beta, paced to its limit (~3.5 req/s), single thread, with retries.
# usage: RPC_URL=... python3 -I fill.py <wallet> <out.json>
import sys, os, json, time, urllib.request, concurrent.futures as cf
sys.argv_ = list(sys.argv)
W, OUT = sys.argv[1], sys.argv[2]
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ledger.py")).read()
g = {"__name__": "ledger_lib", "__file__": "ledger.py"}
exec(src[:src.index("sigs, before = [], None")].replace("W, OUT = sys.argv[1], sys.argv[2]; ", ""), g)
rpc, PUB, one_src = g["rpc"], g["PUB"], None
exec(src[src.index("def one(s):"):src.index("with cf.ThreadPoolExecutor(10) as ex: L =")], g)
g["W"] = W; one = g["one"]
cache = OUT + ".sigs"
if os.path.exists(cache): sigs = json.load(open(cache))
else:
    sigs, before = [], None
    while True:
        p = {"limit": 1000}
        if before: p["before"] = before
        r = rpc("getSignaturesForAddress", [W, p], ep=PUB)
        if not r: break
        sigs += r; before = r[-1]["signature"]; time.sleep(0.5)
        if len(r) < 1000: break
    json.dump(sigs, open(cache, "w"))
prev = {x["sig"]: x for x in json.load(open(OUT))["txs"]} if os.path.exists(OUT) else {}
need = [s for s in sigs if s["signature"] not in prev or prev[s["signature"]].get("missing")]
print(f"{W[:8]}: {len(sigs)} sigs, {len(need)} to fetch", flush=True)
def fast(s):
    t = rpc("getTransaction", [s["signature"], {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}], tries=3)
    return s, t
got = {}
with cf.ThreadPoolExecutor(10) as ex:
    for s, t in ex.map(fast, need):
        if t: got[s["signature"]] = s
# full parse for everything we have; slow public path for the rest
g["rpc"] = rpc
out = dict(prev)
for s in need:
    if s["signature"] in got:
        out[s["signature"]] = one(s)
slow = [s for s in need if s["signature"] not in got]
print(f"   owner RPC had {len(got)}, public path for {len(slow)} older txs (~{len(slow) / 3:.0f} s)", flush=True)
for i, s in enumerate(slow):
    t = None
    for k in range(6):
        t = rpc("getTransaction", [s["signature"], {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}], ep=PUB, tries=1)
        if t: break
        time.sleep(2 + 2 * k)
    if t:
        save_rpc = g["rpc"]; g["rpc"] = lambda m, p, ep=None, tries=8, _t=t: _t
        out[s["signature"]] = one(s); g["rpc"] = save_rpc
    else: out[s["signature"]] = dict(sig=s["signature"], slot=s["slot"], bt=s.get("blockTime"), missing=True)
    time.sleep(0.3)
bal = rpc("getBalance", [W])["value"] / 1e9
hold = []
for prog in ("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"):
    r = rpc("getTokenAccountsByOwner", [W, {"programId": prog}, {"encoding": "jsonParsed"}]) or {"value": []}
    hold += [(a["account"]["data"]["parsed"]["info"]["mint"], a["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"]) for a in r["value"]]
json.dump(dict(wallet=W, balance_now=bal, holdings_now=[h for h in hold if h[1]], txs=list(out.values())), open(OUT, "w"))
print(f"   saved {len(out)} txs, missing {sum(1 for x in out.values() if x.get('missing'))}; balance {bal:.4f}", flush=True)
