#!/usr/bin/env python3
# READ-ONLY. Creator wallet history as of the create (no look-ahead):
#  - prior sigs (before the create sig, capped 1000): count, oldest/newest slot+time
#  - prior launches = prior sigs that are mint-authority create sigs (csigs.jsonl), their mints, and how each had done
#    BY THE TIME of this create (sig count on that mint before this create sig, latest vsol)
#  - SOL funders (oldest txs, and the most recent ones for short histories), funder sig count (cap 1000)
# usage: creator.py <blk jsonl files...>   -> creator.jsonl
import sys, json, os, threading, time, collections
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/indep")
from common import rpc, events
sys.path.insert(0, "/root/nob")
from nrpc import rpc, stats

OUT = "/root/nob/creator.jsonl"
csig = {}
for l in open("/root/nob/csigs.jsonl"):
    x = json.loads(l)
    if not x["err"]:
        csig[x["signature"]] = x["slot"]
recs = {}
for f in sys.argv[1:]:
    for l in open(f):
        r = json.loads(l)
        if r.get("missing"):
            continue
        recs[r["mint"]] = r
done = set()
if os.path.exists(OUT):
    for l in open(OUT):
        try:
            done.add(json.loads(l)["mint"])
        except Exception:
            pass
todo = [r for m, r in recs.items() if m not in done]
print("todo", len(todo), flush=True)
out = open(OUT, "a")
lk = threading.Lock()
cnt = collections.Counter()
fcache = {}
flk = threading.Lock()


def gtxp(sig):
    return rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])


def gtx(sig):
    return rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])


def sol_sources(t, w):
    srcs = []
    if not isinstance(t, dict) or "transaction" not in t:
        return srcs
    msg = t["transaction"]["message"]
    ixs = list(msg.get("instructions") or [])
    for inn in (t.get("meta") or {}).get("innerInstructions") or []:
        ixs += inn.get("instructions") or []
    for ix in ixs:
        p = ix.get("parsed")
        if isinstance(p, dict) and ix.get("program") == "system":
            info = p.get("info") or {}
            if p.get("type") in ("transfer", "transferWithSeed") and info.get("destination") == w:
                srcs.append((info.get("source"), int(info.get("lamports", 0))))
            elif p.get("type") in ("createAccount", "createAccountWithSeed") and info.get("newAccount") == w:
                srcs.append((info.get("source"), int(info.get("lamports", 0))))
    return srcs


def funder_info(f):
    with flk:
        if f in fcache:
            return fcache[f]
    r = rpc("getSignaturesForAddress", [f, {"limit": 1000}])
    v = {"n": len(r) if isinstance(r, list) else None}
    if isinstance(r, list) and r:
        v["span_slots"] = r[0]["slot"] - r[-1]["slot"]
    with flk:
        fcache[f] = v
    return v


def work(r):
    w = r["creator"]
    rec = {"mint": r["mint"], "creator": w, "slot": r["slot"]}
    sig = r["csig"]
    p = rpc("getSignaturesForAddress", [w, {"before": sig, "limit": 1000}])
    if not isinstance(p, list):
        rec["err"] = str(p)[:100]
    else:
        rec["n_prior"] = len(p)
        rec["n_prior_ok"] = sum(1 for x in p if x.get("err") is None)
        if p:
            rec["newest_slot"], rec["newest_bt"] = p[0]["slot"], p[0].get("blockTime")
            rec["oldest_slot"], rec["oldest_bt"] = p[-1]["slot"], p[-1].get("blockTime")
        # prior launches
        pl = [x for x in p if x["signature"] in csig and x.get("err") is None]
        rec["n_prior_launch"] = len(pl)
        if pl:
            rec["last_launch_slot"] = pl[0]["slot"]
        pri = []
        for x in pl[:3]:
            t = gtx(x["signature"])
            if not isinstance(t, dict) or "meta" not in t:
                continue
            tr, cr = events(t["meta"].get("logMessages"))
            if not cr:
                continue
            pm = cr[0]["mint"]
            s2 = rpc("getSignaturesForAddress", [pm, {"before": sig, "limit": 1000}])
            n2 = len(s2) if isinstance(s2, list) else None
            vs = None
            if isinstance(s2, list):
                for y in s2[:4]:
                    if y.get("err") is None:
                        t2 = gtx(y["signature"])
                        if isinstance(t2, dict) and "meta" in t2:
                            tr2, _ = events(t2["meta"].get("logMessages"))
                            ev = [e for e in tr2 if e["mint"] == pm]
                            if ev:
                                vs = ev[-1]["vsol"]
                                break
            pri.append({"mint": pm, "slot": x["slot"], "n_sig_before": n2, "vsol_latest": vs})
        rec["prior"] = pri
        # funders
        pick = []
        if 0 < len(p) < 1000:
            pick.append(p[-1]["signature"])
            if len(p) > 1:
                pick.append(p[-2]["signature"])
        pick += [x["signature"] for x in p[:3] if x["signature"] not in pick]
        fund = []
        for s in pick:
            t = gtxp(s)
            for src, lam in sol_sources(t, w):
                fund.append([src, lam, s[:12], t.get("slot") if isinstance(t, dict) else None])
        rec["fund"] = fund
        fs = {}
        for src, lam, _, _ in fund:
            if src and src != w:
                fs[src] = funder_info(src)
        rec["funders"] = fs
    with lk:
        out.write(json.dumps(rec) + "\n")
        out.flush()
        cnt["done"] += 1
        if cnt["done"] % 200 == 0:
            print(time.strftime("%H:%M:%S"), cnt["done"], "/", len(todo), stats, flush=True)


with ThreadPoolExecutor(max_workers=8) as ex:
    list(ex.map(work, todo))
print("FINISHED", cnt["done"], flush=True)
