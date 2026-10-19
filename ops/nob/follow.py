#!/usr/bin/env python3
# READ-ONLY. Every trade of the mint in slots S+1..S+25 (first 10 s after the create slot) for his no-bundle picks and for
# rule-matched random peers (not mayhem, dev>=0.5 SOL), to identify wallets that follow him. out: follow.jsonl
import sys, json, os, threading, time, bisect, collections
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/indep")
from common import events
sys.path.insert(0, "/root/nob")
from nrpc import rpc, stats

D = "/root/nob/"
OUT = D + "follow.jsonl"
LIM = 25
CAP = 150
anc = []
for l in open(D + "csigs.jsonl"):
    x = json.loads(l)
    anc.append((x["slot"], x["signature"]))
anc.sort()
anc_slots = [a[0] for a in anc]
rows = [json.loads(l) for l in open(D + "ds.jsonl")]
blk = {}
for f in ("blk_rand.jsonl", "blk_rand2.jsonl", "blk_his.jsonl"):
    for l in open(D + f):
        r = json.loads(l)
        if not r.get("missing"):
            blk.setdefault(r["mint"], r)
tg = []
for f in rows:
    if f["slot"] < 457_470_000 or f["quote"] or not f["v0_std"] or not f["nb"]:
        continue
    if f["his"] or (f["in_rand"] and not f["mayhem"] and f["dev_sol"] >= 0.5):
        tg.append((f["mint"], blk[f["mint"]]["csig"], f["slot"], "his" if f["his"] else "peer"))
done = set()
if os.path.exists(OUT):
    for l in open(OUT):
        try:
            done.add(json.loads(l)["mint"])
        except Exception:
            pass
tg = [t for t in tg if t[0] not in done]
print("todo", len(tg), flush=True)
out = open(OUT, "a")
lk = threading.Lock()
cnt = collections.Counter()


def work(t):
    mint, csig, S, grp = t
    i = bisect.bisect_left(anc_slots, S + LIM + 2)
    before = anc[i][1] if i < len(anc) else None
    prm = {"limit": 1000, "until": csig}
    if before:
        prm["before"] = before
    r = rpc("getSignaturesForAddress", [mint, prm])
    rec = {"mint": mint, "slot": S, "grp": grp}
    if not isinstance(r, list):
        rec["err"] = str(r)[:100]
        r = []
    ok = [x for x in reversed(r) if x.get("err") is None and S < x["slot"] <= S + LIM]
    rec["n_ok"] = len(ok)
    if len(ok) > CAP:
        early = [x for x in ok if x["slot"] <= S + 8]
        late = [x for x in ok if x["slot"] > S + 8]
        k = max(0, CAP - len(early))
        step = len(late) / k if k else 1e9
        ok = early[:CAP] + ([late[int(j * step)] for j in range(k)] if k else [])
        rec["sampled"] = True
    tr_rows = []
    for x in ok:
        tx = rpc("getTransaction", [x["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
        if not isinstance(tx, dict) or "meta" not in tx:
            continue
        ev, _ = events((tx.get("meta") or {}).get("logMessages"))
        for e in ev:
            if e["mint"] == mint:
                tr_rows.append([x["slot"], e["buy"], e["user"], e["sol"], e["vsol"]])
    rec["tr"] = tr_rows
    with lk:
        out.write(json.dumps(rec) + "\n")
        out.flush()
        cnt["done"] += 1
        if cnt["done"] % 100 == 0:
            print(time.strftime("%H:%M:%S"), dict(cnt), "/", len(tg), stats, flush=True)


with ThreadPoolExecutor(max_workers=10) as ex:
    list(ex.map(work, tg))
print("FINISHED", dict(cnt), flush=True)
