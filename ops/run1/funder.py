# READ-ONLY (host; public RPCs): who funded each wallet? Walks the wallet's history back to its OLDEST transactions
# and reports the first SOL senders into it (system transfers / balance increases where another signer paid).
# usage: python3 funder.py <wallet> [<wallet> ...]      RPC_URLS as in bundlestudy.py
import sys, os, json, time, itertools, threading, urllib.request

EPS = os.environ.get("RPC_URLS", "https://solana-rpc.publicnode.com,https://api.mainnet-beta.solana.com").split(",")
_rr = itertools.cycle(range(len(EPS))); _lock = threading.Lock()


def rpc(meth, params, tries=10):
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": meth, "params": params}).encode()
    for i in range(tries):
        with _lock: ep = EPS[next(_rr)]
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(ep, data=data, headers={"content-type": "application/json"}), timeout=60))
            if "error" in r: time.sleep(1 + i); continue
            return r.get("result")
        except Exception:
            time.sleep(1 + i)
    return None


def oldest(w, pages=20):
    sigs, before = [], None
    for _ in range(pages):
        p = {"limit": 1000}
        if before: p["before"] = before
        r = rpc("getSignaturesForAddress", [w, p])
        if not r: break
        sigs += r; before = r[-1]["signature"]
        if len(r) < 1000: return sigs, True
    return sigs, False


def funders(w, n=3):
    sigs, complete = oldest(w)
    out = []
    for s in reversed(sigs[-n:] if len(sigs) >= n else sigs):     # oldest first
        t = rpc("getTransaction", [s["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1}])
        if not t: continue
        msg = t["transaction"]["message"]; meta = t["meta"]
        keys = list(msg["accountKeys"]) + (meta.get("loadedAddresses") or {}).get("writable", []) + (meta.get("loadedAddresses") or {}).get("readonly", [])
        if w not in keys: continue
        i = keys.index(w)
        gain = (meta["postBalances"][i] - meta["preBalances"][i]) / 1e9
        out.append(dict(slot=t["slot"], time=t.get("blockTime"), payer=keys[0], gain=gain, sig=s["signature"]))
    return dict(wallet=w, n_txs=len(sigs), history_complete=complete, first=out)


for w in sys.argv[1:]:
    f = funders(w)
    print(f"{w[:8]}  txs {f['n_txs']}{'' if f['history_complete'] else '+'}  first: " +
          "; ".join(f"{x['payer'][:8]} {'->' if x['payer'] != w else 'self'} {x['gain']:+.3f} SOL @ {time.strftime('%m-%d %H:%M', time.gmtime(x['time'])) if x['time'] else '?'}" for x in f["first"]), flush=True)
