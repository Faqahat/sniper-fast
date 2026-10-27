#!/usr/bin/env python3
# Step 2 of 3 for "are the dumpers related to the dev?" (owner 10-25 ~16:45 PKT). Read-only RPC (CK URL from
# ~/.config/sniper/ck_rpc_url, never printed), ~6 req/s. For every wallet of interest (devs, dumpers, wallets that sold
# >= 0.05 SOL while we held, launch-bundle and launch-slot buyers) find WHO FUNDED IT: its oldest transaction (up to 4,000
# signatures back; busier wallets = "busy", no funder) and the SOL transfer into it there. Funders seen for 2+ traced
# wallets are then checked for being a busy hub (an exchange / service): 1,000 signatures inside 6 h.
# out: out/fund.json (cached; rerun continues where it stopped)
import json, os, time, threading, urllib.request
from concurrent.futures import ThreadPoolExecutor
D = os.path.dirname(os.path.abspath(__file__)); OUT = f"{D}/out"
URL = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
PUBLIC = "https://api.mainnet-beta.solana.com"   # full-history archive; only for old txs our RPC no longer keeps, <= 2 req/s
RPS = float(os.environ.get("RPS", "6")); lock = threading.Lock(); nxt = {URL: 0.0, PUBLIC: 0.0}
def rpc(m, p, tries=5, url=URL):
    for i in range(tries):
        with lock:
            t = max(time.time(), nxt[url]); nxt[url] = t + 1 / (RPS if url == URL else 2.0)
        time.sleep(max(0, t - time.time()))
        try:
            req = urllib.request.Request(url, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(),
                                         headers={"content-type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=40))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(1.0 * (i + 1))
    return "ERR"
def get_tx(sig):
    t = rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}], tries=2)
    if t in ("ERR", None) and not os.environ.get("PUBLIC_OFF"):   # PUBLIC_OFF=1 when the public RPC rate-limits us (HTTP 429)
        t = rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}], tries=4, url=PUBLIC)
    return None if t == "ERR" else t
def transfers_in(t, w):
    keys = [k["pubkey"] if isinstance(k, dict) else k for k in t["transaction"]["message"]["accountKeys"]]
    ixs = list(t["transaction"]["message"].get("instructions") or [])
    for g in (t.get("meta") or {}).get("innerInstructions") or []: ixs += g.get("instructions") or []
    best = None
    for ix in ixs:
        pa = ix.get("parsed") if isinstance(ix, dict) else None
        if not isinstance(pa, dict) or ix.get("program") != "system": continue
        info = pa.get("info") or {}
        dst = info.get("destination") or info.get("newAccount"); src = info.get("source")
        lam = int(info.get("lamports") or 0)
        if dst == w and src and src != w and (best is None or lam > best[1]): best = (src, lam, pa.get("type"))
    return keys, best
def funder_of(w, pages=4):
    before = None; n = 0; last = None
    for _ in range(pages):
        p = {"limit": 1000}
        if before: p["before"] = before
        r = rpc("getSignaturesForAddress", [w, p])
        if r == "ERR": return {"err": "sigs"}
        n += len(r)
        if r: last = r[-1]
        if len(r) < 1000: break
        before = r[-1]["signature"]
    else:
        return {"busy": True, "n": n, "oldest_seen": last and last.get("blockTime")}
    if not last: return {"n": 0}
    # oldest first: the first SOL top-up (>= 0.005 SOL) in the wallet's first 4 txs = its funder (dust/spam txs come first sometimes)
    old = (r if len(r) < 1000 else r)[-4:][::-1] if r else [last]
    out = {"n": n, "first_sig": last["signature"], "first_t": last.get("blockTime"), "first_slot": last.get("slot")}
    fee_payer = None
    for k, x in enumerate(old):
        t = get_tx(x["signature"])
        if not t: continue
        keys, best = transfers_in(t, w)
        if k == 0 or fee_payer is None: fee_payer = keys[0] if keys else None
        if best and best[1] >= 5_000_000:
            out.update(funder=best[0], lamports=best[1], how=best[2], fund_sig=x["signature"], fund_t=t.get("blockTime")); return out
    if fee_payer is None: out["err"] = "tx"; return out
    out["fee_payer"] = fee_payer
    if fee_payer != w: out.update(funder=fee_payer, how="fee_payer")
    return out
def hub_check(f):
    r = rpc("getSignaturesForAddress", [f, {"limit": 1000}])
    if r == "ERR" or not r: return {"err": True}
    ts = [x.get("blockTime") for x in r if x.get("blockTime")]
    span = (max(ts) - min(ts)) if ts else None
    return {"n": len(r), "span_s": span, "hub": len(r) >= 1000 and span is not None and span < 6 * 3600}
if __name__ == "__main__":
    W = json.load(open(f"{OUT}/wallets.json"))       # written by dev_link.py --wallets
    cache = json.load(open(f"{OUT}/fund.json")) if os.path.exists(f"{OUT}/fund.json") else {"w": {}, "hub": {}}
    redo = os.environ.get("REDO")       # REDO=1: retrace errors and the weak "fee_payer"/"balance" answers with the newer method
    todo = [w for w in W if w not in cache["w"] or "err" in cache["w"][w]
            or (redo and not cache["w"][w].get("v2") and not cache["w"][w].get("busy")
                and (cache["w"][w].get("how") in ("fee_payer", "balance") or (cache["w"][w].get("lamports") or 0) < 5_000_000))]
    print(len(W), "wallets,", len(todo), "to trace", flush=True)
    done = [0]
    def job(w):
        r = funder_of(w); r["v2"] = True
        with lock:
            cache["w"][w] = r; done[0] += 1
            if done[0] % 50 == 0:
                json.dump(cache, open(f"{OUT}/fund.json", "w")); print(done[0], "traced", flush=True)
    with ThreadPoolExecutor(4) as ex: list(ex.map(job, todo))
    json.dump(cache, open(f"{OUT}/fund.json", "w"))
    from collections import Counter
    c = Counter(r.get("funder") for r in cache["w"].values() if r.get("funder"))
    hubs = [f for f, k in c.items() if k >= 2 and f not in cache["hub"]]
    print(len(hubs), "shared funders to hub-check", flush=True)
    with ThreadPoolExecutor(4) as ex:
        for f, r in zip(hubs, ex.map(hub_check, hubs)): cache["hub"][f] = r
    json.dump(cache, open(f"{OUT}/fund.json", "w"))
    print("done", sum(1 for r in cache["w"].values() if r.get("funder")), "funders found,",
          sum(1 for r in cache["w"].values() if r.get("busy")), "busy wallets", flush=True)
