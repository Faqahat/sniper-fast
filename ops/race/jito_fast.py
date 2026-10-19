#!/usr/bin/env python3
# READ-ONLY public GETs (bundles.jito.wtf). Were the FAST outside buyers (independent, same slot, <= 25 txs behind the
# create) and 4yFAz's buys inside a Jito bundle, i.e. a backrun bundle on the create? Sample: /root/indep/buyers.jsonl.
# Output: /root/race/jito_fast.json {sig: {in_bundle, bundle_id, txs, tippers, landedTipLamports}}
import json, os, time, urllib.request
OUT = "/root/race/jito_fast.json"
W = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
res = json.load(open(OUT)) if os.path.exists(OUT) else {}


def get(url):
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={"user-agent": "research (read-only)"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"__404": True}
            time.sleep(2 * (i + 1))
        except Exception:
            time.sleep(2 * (i + 1))
    return None


B = [json.loads(l) for l in open("/root/indep/buyers.jsonl")]
todo = []
for b in B:
    if b.get("sd") != 0:
        continue
    fast_indep = b.get("cls") == "INDEP" and b["off"] <= 25
    his = b.get("user") == W or b.get("payer") == W
    mid_indep = b.get("cls") == "INDEP" and 26 <= b["off"] <= 150 and sum(map(ord, b["sig"])) % 4 == 0   # comparison sample
    if (fast_indep or his or mid_indep) and b["sig"] not in res:
        todo.append(b["sig"])
todo = list(dict.fromkeys(todo))
print("todo", len(todo), flush=True)
for i, sig in enumerate(todo):
    a = get(f"https://bundles.jito.wtf/api/v1/bundles/transaction/{sig}")
    rec = {"in_bundle": False}
    if isinstance(a, list) and a:
        bid = a[0].get("bundle_id")
        rec = {"in_bundle": True, "bundle_id": bid}
        bb = get(f"https://bundles.jito.wtf/api/v1/bundles/bundle/{bid}")
        if isinstance(bb, list) and bb:
            bb = bb[0]
        if isinstance(bb, dict):
            rec["txs"] = bb.get("txSignatures") or bb.get("transactions")
            rec["tippers"] = bb.get("tippers")
            rec["landedTipLamports"] = bb.get("landedTipLamports")
    elif a is None:
        rec = {"err": True}
    res[sig] = rec
    if i % 20 == 0:
        json.dump(res, open(OUT, "w"))
        print(i, flush=True)
    time.sleep(0.5)
json.dump(res, open(OUT, "w"))
print("FINISHED", len(res), flush=True)
