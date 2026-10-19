#!/usr/bin/env python3
# READ-ONLY. Stage 3: ask the public Jito bundle explorer whether each create tx (that has a buy right behind it)
# landed inside a Jito bundle, and which txs that bundle contained. ~1 req/s.
# usage: bundles.py <creates.jsonl> <out.json>
import json, sys, time, urllib.request, os

INP, OUT = sys.argv[1], sys.argv[2]
res = json.load(open(OUT)) if os.path.exists(OUT) else {}


def get(url):
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={"user-agent": "research"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"__404": True}
            time.sleep(2 * (i + 1))
        except Exception:
            time.sleep(2 * (i + 1))
    return None


todo = []
for l in open(INP):
    try:
        r = json.loads(l)
    except Exception:
        continue
    if r.get("missing"):
        continue
    nb = sorted(r["nb"], key=lambda x: x["d"])
    glued = any(x["d"] in (1, 2) and x["mint_ev"] > 0 for x in nb) or any(e["buy"] and e["user"] != r["cev"]["creator"] for e in r["create"]["ev"])
    if glued and r["create"]["sig"] not in res:
        todo.append(r["create"]["sig"])
print("todo", len(todo), flush=True)
for i, sig in enumerate(todo):
    a = get(f"https://bundles.jito.wtf/api/v1/bundles/transaction/{sig}")
    rec = {"in_bundle": False}
    if isinstance(a, list) and a:
        bid = a[0].get("bundle_id")
        rec = {"in_bundle": True, "bundle_id": bid}
        b = get(f"https://bundles.jito.wtf/api/v1/bundles/bundle/{bid}")
        time.sleep(0.6)
        if isinstance(b, list) and b:
            b = b[0]
        if isinstance(b, dict):
            rec["txs"] = b.get("txSignatures") or b.get("transactions") or []
            rec["tippers"] = b.get("tippers")
            rec["landedTipLamports"] = b.get("landedTipLamports")
    elif a is None:
        rec = {"in_bundle": None}
    res[sig] = rec
    time.sleep(0.6)
    if i % 25 == 0:
        json.dump(res, open(OUT, "w"))
        print(i, sum(1 for v in res.values() if v.get("in_bundle")), flush=True)
json.dump(res, open(OUT, "w"))
print("FINISHED", len(res), sum(1 for v in res.values() if v.get("in_bundle")), flush=True)
