#!/usr/bin/env python3
"""Long run: did winners land through Jito bundles? For up to N clean wins per top bot (wins.jsonl.gz), ask Jito's
bundle explorer API (bundles.jito.wtf, undocumented, research log S-011) whether the transaction was in a bundle, and
if so the bundle's size, tip and position. A win in the same bundle as its trigger = owning the order flow.
usage: bundles.py <per bot> <top bots> -> bundles.json"""
import json, sys, gzip, collections, time, urllib.request

PER, TOP = int(sys.argv[1]), int(sys.argv[2])
bots = json.load(open("bots.json"))
top = [b["signer"] for b in sorted(bots.values(), key=lambda b: -b["wins"])[:TOP]]
by = collections.defaultdict(list)
for l in gzip.open("wins.jsonl.gz", "rt"):
    w = json.loads(l)
    if w["signer"] in top and len(by[w["signer"]]) < PER: by[w["signer"]].append(w)

def get(url):
    for i in range(3):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"user-agent": "arb-lab research"}), timeout=20))
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            time.sleep(2 + 3 * i)
        except Exception:
            time.sleep(2 + 3 * i)
    return "error"

out = {}
for b, ws in by.items():
    rows = []
    for w in ws:
        r = get(f"https://bundles.jito.wtf/api/v1/bundles/transaction/{w['sig']}")
        time.sleep(0.4)
        row = {"sig": w["sig"], "trig": w["trig"], "in_bundle": None}
        if r == "error": row["in_bundle"] = "error"
        elif not r: row["in_bundle"] = False
        else:
            bid = r[0]["bundle_id"] if isinstance(r, list) else r.get("bundle_id")
            d = get(f"https://bundles.jito.wtf/api/v1/bundles/bundle/{bid}")
            time.sleep(0.4)
            if isinstance(d, list): d = d[0] if d else None
            row["in_bundle"] = True; row["bundle"] = d if isinstance(d, (dict, list)) else bid
            txs = (d or {}).get("txSignatures") if isinstance(d, dict) else None
            if isinstance(d, dict): row["bundle_size"] = len(txs or []); row["tip"] = d.get("landedTipLamports"); row["block_index"] = d.get("blockIndex")
            if txs and w["trig"]: row["trigger_in_same_bundle"] = w["trig"]["sig"] in txs
        rows.append(row)
    n = len(rows); nb = sum(1 for r in rows if r["in_bundle"] is True)
    out[b] = {"checked": n, "in_bundle": nb, "errors": sum(1 for r in rows if r["in_bundle"] == "error"),
              "trigger_in_same_bundle": sum(1 for r in rows if r.get("trigger_in_same_bundle")), "rows": rows}
    print(f"{b[:8]}: {nb}/{n} wins in a Jito bundle, trigger in the same bundle {out[b]['trigger_in_same_bundle']}, errors {out[b]['errors']}", flush=True)
json.dump(out, open("bundles.json", "w"))
