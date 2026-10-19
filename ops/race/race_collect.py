#!/usr/bin/env python3
# READ-ONLY. For each launch in /root/nob (blk_rand*, blk_his): every signature on the mint in slots S..S+8
# (getSignaturesForAddress paged between an anchor just after S+8 and the create sig), plus getTransaction of every
# OK tx in S+1..S+5 (cap per launch) -> payer, trade events on the mint, priority fee, cu price, tips, signers.
# Slot S itself is already complete in blk_*.jsonl ("later"), in block order.
# usage: race_collect.py <out.jsonl> [workers]
import sys, json, os, threading, time, bisect, collections
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/indep")
from common import events, tx_summary, load_tipmap
sys.path.insert(0, "/root/nob")
from nrpc import rpc, stats

OUT = sys.argv[1]
NW = int(sys.argv[2]) if len(sys.argv) > 2 else 8
WIN = 8          # slots after S to list
FETCH_TO = 5     # fetch txs in S+1..S+FETCH_TO
CAP = 90         # max txs fetched per launch
tipmap = load_tipmap()
anc = []
for l in open("/root/nob/csigs.jsonl"):
    x = json.loads(l)
    anc.append((x["slot"], x["signature"]))
anc.sort()
anc_slots = [a[0] for a in anc]
quote = {}
for l in open("/root/nob/ds.jsonl"):
    r = json.loads(l)
    quote[r["mint"]] = r["quote"]
tg = []
seen = set()
for fn in ("blk_rand.jsonl", "blk_rand2.jsonl", "blk_his.jsonl"):
    for l in open("/root/nob/" + fn):
        try:
            r = json.loads(l)
        except Exception:
            continue
        m = r.get("mint")
        if not m or m in seen or quote.get(m, True):
            continue
        seen.add(m)
        tg.append({"mint": m, "csig": r["csig"], "slot": r["slot"]})
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
tg.sort(key=lambda t: t["slot"])
print("todo", len(tg), flush=True)
out = open(OUT, "a")
lk = threading.Lock()
cnt = collections.Counter()


def anchor(S):
    i = bisect.bisect_left(anc_slots, S + WIN + 1)
    return anc[i][1] if i < len(anc) else None


def work(t):
    mint, csig, S = t["mint"], t["csig"], t["slot"]
    rec = {"mint": mint, "slot": S}
    before = anchor(S)
    sigs, pages = [], 0
    while True:
        prm = {"limit": 1000, "until": csig}
        if before:
            prm["before"] = before
        r = rpc("getSignaturesForAddress", [mint, prm], tries=10)
        pages += 1
        if not isinstance(r, list):
            rec["sig_err"] = str(r)[:100]
            break
        sigs += r
        if len(r) < 1000 or pages >= 6:
            break
        before = r[-1]["signature"]
    if "sig_err" in rec:
        with lk:
            out.write(json.dumps(rec) + "\n"); out.flush(); cnt["err"] += 1
        return
    sigs = [x for x in reversed(sigs) if S <= x["slot"] <= S + WIN]
    rec["pages"] = pages
    rec["act"] = sorted(collections.Counter(x["slot"] - S for x in sigs if x.get("err") is None).items())
    rec["act_err"] = sorted(collections.Counter(x["slot"] - S for x in sigs if x.get("err") is not None).items())
    pick = [x for x in sigs if x.get("err") is None and 1 <= x["slot"] - S <= FETCH_TO]
    rec["n_pick"] = len(pick)
    pick = pick[:CAP]
    rows = []
    for x in pick:
        tx = rpc("getTransaction", [x["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
        if not isinstance(tx, dict) or "meta" not in tx:
            rows.append({"d": x["slot"] - S, "sig": x["signature"][:16], "miss": 1})
            continue
        try:
            s, keys = tx_summary(tx, tipmap)
        except Exception:
            rows.append({"d": x["slot"] - S, "sig": x["signature"][:16], "miss": 2})
            continue
        tr, _ = events((tx.get("meta") or {}).get("logMessages"))
        ev = [[e["buy"], e["user"], e["sol"], e["tok"], e["vsol"]] for e in tr if e["mint"] == mint]
        rows.append({"d": x["slot"] - S, "sig": x["signature"][:16], "payer": s["payer"], "nsig": len(s["signers"]),
                     "fee": s["fee"], "cu_price": s["cu_price"], "cu_limit": s["cu_limit"], "tips": [[a[0], a[1]] for a in s["tips"]],
                     "bt": tx.get("blockTime"), "ev": ev})
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
print("FINISHED", dict(cnt), stats, flush=True)
