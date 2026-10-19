#!/usr/bin/env python3
# READ-ONLY. Stage 2: wallet history for every creator and every buyer (create slot + next block) in creates.jsonl.
# For each wallet: number of txs before its first appearance (capped 1000), first/last prior blockTime, and the SOL
# funders (sources of SOL transfers into it) from its oldest tx and its most recent prior txs.
# usage: wallets.py <creates.jsonl> <out.jsonl> [workers]
import json, sys, threading, time, collections, os
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/indep")
from common import *

INP, OUT = sys.argv[1], sys.argv[2]
W = int(sys.argv[3]) if len(sys.argv) > 3 else 8
done = set()
if os.path.exists(OUT):
    for l in open(OUT):
        try:
            done.add(json.loads(l)["w"])
        except Exception:
            pass

ref = {}  # wallet -> (slot, sig, role)
for l in open(INP):
    try:
        r = json.loads(l)
    except Exception:
        continue
    if r.get("missing"):
        continue
    nbuy = sum(1 for x in r["rows"] + r["nrows"] for e in x["ev"] if e["buy"]) + sum(1 for e in r["create"]["ev"] if e["buy"] and e["user"] != r["cev"]["creator"])
    if nbuy == 0:
        continue
    cr = r["cev"]["creator"]
    cands = [(cr, r["slot"], r["create"]["sig"], "creator")]
    if r["create"]["payer"] != cr:
        cands.append((r["create"]["payer"], r["slot"], r["create"]["sig"], "creator_payer"))
    for e in r["create"]["ev"]:
        if e["buy"] and e["user"] != cr:
            cands.append((e["user"], r["slot"], r["create"]["sig"], "buyer"))
    nxt = r["next"][0]["slot"] if r["next"] else None
    for x in r["rows"] + [x for x in r["nrows"] if x["slot"] == nxt or (r.get("ours") and x["sig"] == r["ours"].get("sig"))]:
        for e in x["ev"]:
            if e["buy"]:
                cands.append((e["user"], x["slot"], x["sig"], "buyer"))
    for w, s, sig, role in cands:
        if w not in ref or s < ref[w][0]:
            ref[w] = (s, sig, role if w not in ref else ref[w][2] if ref[w][2] == "creator" else role)
todo = [(w, v) for w, v in ref.items() if w not in done]
print(f"wallets {len(ref)} todo {len(todo)}", flush=True)


def sol_sources(t, w):
    """SOL sources into wallet w in a jsonParsed tx: transfer sources (top + inner) else fee payer"""
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
    if not srcs:
        keys = [k["pubkey"] if isinstance(k, dict) else k for k in msg["accountKeys"]]
        if keys and keys[0] != w:
            try:
                i = keys.index(w)
                d = t["meta"]["postBalances"][i] - t["meta"]["preBalances"][i]
                if d > 0:
                    srcs.append((keys[0], d))
            except Exception:
                pass
    return srcs


out = open(OUT, "a")
lk = threading.Lock()
cnt = collections.Counter()


def gtx(sig):
    return rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])


def work(item):
    w, (slot, sig, role) = item
    rec = {"w": w, "role": role, "ref_slot": slot, "ref_sig": sig}
    r = rpc("getSignaturesForAddress", [w, {"before": sig, "limit": 1000}])
    if not isinstance(r, list):
        rec["err"] = str(r)[:100]
    else:
        rec["n_prior"] = len(r)
        if r:
            rec["last_prior_bt"] = r[0].get("blockTime")
            rec["last_prior_slot"] = r[0].get("slot")
            rec["oldest_bt"] = r[-1].get("blockTime")
            rec["oldest_slot"] = r[-1].get("slot")
            fund = []
            pick = []
            if len(r) < 1000:
                pick.append(r[-1]["signature"])
                if len(r) > 1:
                    pick.append(r[-2]["signature"])
            if len(r) <= 40:
                pick += [x["signature"] for x in r[:4]]
            seen = set()
            for s in pick:
                if s in seen:
                    continue
                seen.add(s)
                t = gtx(s)
                for src, lam in sol_sources(t, w):
                    fund.append([src, lam, s[:16], t.get("blockTime") if isinstance(t, dict) else None])
            rec["fund"] = fund
    with lk:
        out.write(json.dumps(rec) + "\n")
        out.flush()
        cnt["done"] += 1
        if cnt["done"] % 200 == 0:
            print(f"{time.strftime('%H:%M:%S')} {cnt['done']}/{len(todo)}", flush=True)


with ThreadPoolExecutor(max_workers=W) as ex:
    list(ex.map(work, todo))
print("FINISHED", cnt["done"], flush=True)
