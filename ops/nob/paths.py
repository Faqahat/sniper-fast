#!/usr/bin/env python3
# READ-ONLY. Price path over the first ~60 s (150 slots) of each launch.
# Sigs: getSignaturesForAddress(mint, before=<anchor sig just after S+155>, until=<create sig>) so we only page the window.
# Txs: last ok tx of each slot S+1..S+30, then of each 3-slot bucket to S+150; parse TradeEvents (slot S comes from the block).
# usage: paths.py <targets.json: [{mint,csig,slot}]> <out.jsonl> [workers]
import sys, json, os, threading, time, bisect, collections
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/indep")
from common import rpc, events
sys.path.insert(0, "/root/nob")
from nrpc import rpc, stats

INP, OUT = sys.argv[1], sys.argv[2]
NW = int(sys.argv[3]) if len(sys.argv) > 3 else 10
WIN = 150
DENSE = 25
CAP = int(os.environ.get("NOB_CAP", "150"))
anc = []
for l in open("/root/nob/csigs.jsonl"):
    x = json.loads(l)
    anc.append((x["slot"], x["signature"]))
anc.sort()
anc_slots = [a[0] for a in anc]
tg = json.load(open(INP))
done = set()
if os.path.exists(OUT):
    for l in open(OUT):
        try:
            x = json.loads(l)
            if "sig_err" not in x:
                done.add(x["mint"])
        except Exception:
            pass
tg = [t for t in tg if t["mint"] not in done]
print("todo", len(tg), flush=True)
out = open(OUT, "a")
lk = threading.Lock()
cnt = collections.Counter()


def anchor(S):
    i = bisect.bisect_left(anc_slots, S + WIN + 5)
    return anc[i][1] if i < len(anc) else None


def work(t):
    mint, csig, S = t["mint"], t["csig"], t["slot"]
    rec = {"mint": mint, "slot": S}
    before = anchor(S)
    sigs = []
    pages = 0
    while True:
        prm = {"limit": 1000, "until": csig}
        if before:
            prm["before"] = before
        r = rpc("getSignaturesForAddress", [mint, prm], tries=8)
        pages += 1
        if not isinstance(r, list):
            rec["sig_err"] = str(r)[:100]
            break
        sigs += r
        if len(r) < 1000 or pages >= 20:
            break
        before = r[-1]["signature"]
    rec["pages"] = pages
    # RPC order: newest first; within a slot assume descending tx index -> reverse whole list for chronological order
    sigs = [x for x in reversed(sigs) if x["slot"] <= S + WIN]
    rec["n_sig"] = len(sigs)
    rec["n_err"] = sum(1 for x in sigs if x.get("err") is not None)
    ok = [x for x in sigs if x.get("err") is None]
    rec["n_ok"] = len(ok)
    rec["n_ok_dense"] = sum(1 for x in ok if x["slot"] <= S + DENSE)
    # last ok tx of each slot S+1..S+30, then last ok tx of each 3-slot bucket up to S+150 (block order = reversed RPC order)
    last_by_bucket = {}
    for x in ok:
        d = x["slot"] - S
        if d <= 0:
            continue
        b = d if d <= 30 else 30 + (d - 31) // 3 * 3 + 3
        last_by_bucket[b] = x
    pick = [last_by_bucket[b] for b in sorted(last_by_bucket)]
    act = collections.Counter(x["slot"] - S for x in ok)
    rec["act"] = sorted(act.items())
    rows = []
    for x in pick:
        tx = rpc("getTransaction", [x["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
        if not isinstance(tx, dict) or "meta" not in tx:
            rows.append([x["slot"], None])
            continue
        tr, _ = events((tx.get("meta") or {}).get("logMessages"))
        keys = tx["transaction"]["message"]["accountKeys"]
        nsig = tx["transaction"]["message"]["header"]["numRequiredSignatures"]
        ev = [[e["buy"], e["user"], e["sol"], e["tok"], e["vsol"]] for e in tr if e["mint"] == mint]
        rows.append([x["slot"], ev, x["signature"][:16], keys[0][:12], tx.get("blockTime")])
    rec["rows"] = rows
    with lk:
        out.write(json.dumps(rec) + "\n")
        out.flush()
        cnt["done"] += 1
        cnt["tx"] += len(pick)
        if cnt["done"] % 100 == 0:
            print(time.strftime("%H:%M:%S"), dict(cnt), "/", len(tg), stats, flush=True)


with ThreadPoolExecutor(max_workers=NW) as ex:
    list(ex.map(work, tg))
print("FINISHED", dict(cnt), flush=True)
