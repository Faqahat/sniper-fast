#!/usr/bin/env python3
# READ-ONLY: market path (every successful pump.fun trade of the mint) from the wallet's buy to its last sell (+ a short tail
# when cheap) for tokens OUTSIDE the collector windows but inside the Constant-K history (slot > ~459.3M). Only successful txs
# (failed spam is ~90% of signatures). Output: cache/paths/<mint>.json  rows like common.trades_of().
# usage: python3 -I fetch_paths.py [min_buy_sol] [max_ok_sigs_per_token]
import sys, os, json, gzip, collections, concurrent.futures as cf
EX = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, EX)
from rpc import rpc, get_tx
from common import WALLETS, decode_events
MIN_BUY = float(sys.argv[1]) if len(sys.argv) > 1 else 2.4; CAP = int(sys.argv[2]) if len(sys.argv) > 2 else 400
OUT = os.path.join(EX, "cache", "paths"); os.makedirs(OUT, exist_ok=True)
A = {(a["w"], a["mint"]) for a in json.load(open(os.path.join(EX, "align.json"))) if not a["coverage"]["missing"]}
todo = []
for w in WALLETS:
    for r in json.load(open(os.path.join(EX, f"roundtrips_{w}.json")))["tokens"]:
        if r["buy_slot"] > 459300000 and (w, r["mint"]) not in A and r["buy_sol"] >= MIN_BUY and r["n_sells"]:
            todo.append((w, r))
todo.sort(key=lambda x: -x[1]["buy_sol"])
print("tokens to fetch", len(todo), flush=True)
def sigs_for(r):
    sells = [l for l in r["legs"] if l["side"] == "sell"]; last = sells[-1]; b0 = r["legs"][0]
    got = []; before = last["sig"]; pages = 0
    while pages < 12:
        res = rpc("getSignaturesForAddress", [r["mint"], {"limit": 1000, "before": before}]); pages += 1
        if not res: break
        got += [s for s in res if s["slot"] >= b0["slot"] - 1]
        if len(res) < 1000 or res[-1]["slot"] < b0["slot"] - 1: break
        before = res[-1]["signature"]
    tail = rpc("getSignaturesForAddress", [r["mint"], {"limit": 1000, "until": last["sig"]}]) or []
    if tail and len(tail) < 1000: got += [s for s in tail if s["slot"] <= last["slot"] + 150]
    ok = sorted([s for s in got if s.get("err") is None], key=lambda s: (s["slot"], s.get("transactionIndex") or 0))
    own = {l["sig"] for l in r["legs"]}
    keep = [s for s in ok if s["signature"] in own] + [s for s in ok if s["signature"] not in own][:CAP]
    return sorted(keep, key=lambda s: (s["slot"], s.get("transactionIndex") or 0)), len(got), len(ok), pages
def one(item):
    w, r = item; m = r["mint"]; p = os.path.join(OUT, m + ".json")
    if os.path.exists(p): return m, "cached"
    keep, n_all, n_ok, pages = sigs_for(r)
    rows = []
    def tx(s):
        t = get_tx(s["signature"])
        if not t: return []
        evs = [e for e in decode_events(t) if e["mint"] == m]
        return [dict(s=t["slot"], i=s.get("transactionIndex") or 0, j=j, bt=t.get("blockTime"), sig=s["signature"], payer=t["transaction"]["message"]["accountKeys"][0]["pubkey"],
                     user=e["user"], buy=e["buy"], sol=e["sol"], tok=e["tok"], vsol=e["vsol"], vtok=e["vtok"], creator=e["creator"]) for j, e in enumerate(evs)]
    with cf.ThreadPoolExecutor(4) as ex:
        for rr in ex.map(tx, keep): rows += rr
    rows.sort(key=lambda t: (t["s"], t["i"], t["j"]))
    json.dump(dict(mint=m, w=w, n_sigs=n_all, n_ok=n_ok, n_kept=len(keep), capped=len(keep) < n_ok, pages=pages, rows=rows), open(p, "w"))
    return m, f"sigs {n_all} ok {n_ok} kept {len(keep)} rows {len(rows)}"
with cf.ThreadPoolExecutor(2) as ex:
    for k, (m, msg) in enumerate(ex.map(one, todo), 1):
        print(k, m[:8], msg, flush=True)
print("DONE", flush=True)
