#!/usr/bin/env python3
# READ-ONLY drill-down on truth_sample.jsonl: creator mismatches, quote-mint location in the create_v2 accounts,
# AFTER false-keeps, failed creates.
import sys, json, collections as C
sys.path.insert(0, "/root/det")
from dlib import *

R = [json.loads(l) for l in open(sys.argv[1])]
ok = [r for r in R if not r.get("err") and not r.get("miss") and not r.get("exc") and not r.get("nocreate") and r.get("ev")]
mis = [r for r in ok if r["args"].get("creator") != r["ev"].get("creator")]
print("creator mismatch", len(mis))
for r in mis[:5]:
    print("  ", r["mint"][:10], "arg", (r["args"].get("creator") or "")[:10], "ev.creator", r["ev"]["creator"][:10], "ev.user", r["ev"]["user"][:10],
          "payer", r["payer"][:10], "trailing", r["args"].get("trailing"), "quote", r["ev"].get("quote_mint", "")[:8], "top", r["top"])
print("  mismatch by quote:", C.Counter(r["ev"].get("quote_mint", "")[:6] for r in mis), "by trailing:", C.Counter(r["args"].get("trailing") for r in mis))
print("  ev.creator == ev.user among mismatches:", sum(r["ev"]["creator"] == r["ev"]["user"] for r in mis))


def tx(sig):
    return rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])


# quote mint location: for 3 SOL and 3 non-SOL creates, print the create ix accounts
for want in ("sol", "non"):
    pick = [r for r in ok if r["top"] and ((r["ev"].get("quote_mint") == "11111111111111111111111111111111") == (want == "sol"))][:3]
    for r in pick:
        t = tx(r["sig"])
        msg = t["transaction"]["message"]
        la = t["meta"].get("loadedAddresses") or {}
        keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
        for ix in msg["instructions"]:
            if keys[ix["programIdIndex"]] != PUMP:
                continue
            d = b58dec(ix["data"])
            if d[:8] == CREATE_V2:
                acc = [keys[i] for i in ix["accounts"]]
                qm = r["ev"].get("quote_mint")
                print(f"{want} {r['mint'][:8]} quote={qm[:8]} n_acc={len(acc)} quote_idx={[i for i, a in enumerate(acc) if a == qm]} depth={r['ev'].get('depth')} trailing={r['args'].get('trailing')}")
                print("    ", [a[:6] for a in acc])
            elif d[:8] in SIZED or d[:8] in CAP:
                acc = [keys[i] for i in ix["accounts"]]
                print(f"    buy {SIZED.get(d[:8]) or CAP.get(d[:8])} n_acc={len(acc)} acc[0:4]={[a[:6] for a in acc[:4]]}")
# depth vs quote
print("depth x quote", C.Counter((r["ev"].get("depth"), r["ev"].get("quote_mint", "")[:6]) for r in ok).most_common(10))
# false keeps
band = lambda x: 0.5e9 <= x <= 8e9
fk = [r for r in ok if not r["bl"] and band(r["dev_after"]) and not band(r["true_dev"])]
print("AFTER false-keeps", len(fk), "by quote", C.Counter(r["ev"].get("quote_mint", "")[:6] for r in fk))
for r in fk[:6]:
    print("  ", r["mint"][:10], "after", r["dev_after"], "true", r["true_dev"], "tok", r["true_dev_tok"], "kinds", r["dev_kinds"][:2], "quote", r["ev"].get("quote_mint", "")[:6])
# failed creates: duplicate of a landed mint?
landed = {r["mint"] for r in ok}
fail = [json.loads(l) for l in open(sys.argv[1])]
fail = [r for r in fail if r.get("err")]
print("failed creates", len(fail), "with a mint that also landed OK in the window:", sum(1 for r in fail if r.get("mint") in landed),
      "kinds", C.Counter(r.get("kind") for r in fail), "top", C.Counter(r.get("top") for r in fail))
nocr = [json.loads(l) for l in open(sys.argv[1])]
print("no-create sigs", [r["sig"][:12] for r in nocr if r.get("nocreate")][:6])
