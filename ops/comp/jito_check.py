# READ-ONLY: for each top-wallet first buy, ask bundles.jito.wtf whether the tx landed inside a Jito bundle (~1 req/s).
import json, sys, time, urllib.request
SET = sys.argv[1] if len(sys.argv) > 1 else "r2"
MAXPER = int(sys.argv[2]) if len(sys.argv) > 2 else 40
T = json.load(open(f"/root/comp/top_{SET}.json"))
out_fn = f"/root/comp/jito_{SET}.json"
try: done = json.load(open(out_fn))
except Exception: done = {}
todo = []
for w in T["tops"]:
    for r in T["rows"].get(w, [])[:MAXPER]:
        if r["sig"] not in done: todo.append(r["sig"])
# also 4yFAz buys (from his tx.jsonl), up to MAXPER
W4 = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
k = 0
for l in open("/root/sizing/tx.jsonl"):
    t = json.loads(l)
    if not t["err"] and any(e["user"] == W4 and e["buy"] for e in t["ev"]) and t["sig"] not in done:
        todo.append(t["sig"]); k += 1
        if k >= MAXPER: break
print("todo", len(todo), flush=True)
for i, s in enumerate(todo):
    try:
        r = json.load(urllib.request.urlopen(urllib.request.Request("https://bundles.jito.wtf/api/v1/bundles/transaction/" + s,
                                                                   headers={"user-agent": "research"}), timeout=15))
        if isinstance(r, list) and r:
            bid = r[0].get("bundle_id", "")
            time.sleep(0.9)
            d = json.load(urllib.request.urlopen(urllib.request.Request("https://bundles.jito.wtf/api/v1/bundles/bundle/" + bid,
                                                                       headers={"user-agent": "research"}), timeout=15))
            d = d[0] if isinstance(d, list) and d else {}
            done[s] = {"bundle": bid[:16], "ntx": len(d.get("txSignatures") or []), "tip": d.get("landedTipLamports"), "tippers": [t[:8] for t in d.get("tippers") or []],
                       "validator": (d.get("validator") or "")[:8], "idx": d.get("blockIndex"), "pos_in_bundle": (d.get("txSignatures") or []).index(s) if s in (d.get("txSignatures") or []) else None}
        else:
            done[s] = {"bundle": None}
    except urllib.error.HTTPError as ex:
        done[s] = {"bundle": None, "http": ex.code}
    except Exception as ex:
        done[s] = {"bundle": None, "err": str(ex)[:80]}
    time.sleep(0.9)
    if i % 25 == 0:
        json.dump(done, open(out_fn, "w")); print(i, flush=True)
json.dump(done, open(out_fn, "w"))
print("DONE", flush=True)
