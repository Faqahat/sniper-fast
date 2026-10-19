#!/usr/bin/env python3
# READ-ONLY: 4yFAz's successful pump buys in a slot window -> <out.jsonl> (mint, slot, sol, sig). Resumable by sig.
# usage: his.py <out.jsonl> <slot_from> <slot_to>
import sys, json, os, threading
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/det")
from dlib import *

OUT, S0, S1 = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
sigs, before, pages = [], None, 0
while True:
    prm = {"limit": 1000}
    if before:
        prm["before"] = before
    r = rpc("getSignaturesForAddress", [W4, prm])
    pages += 1
    if not isinstance(r, list) or not r:
        break
    sigs += [x for x in r if S0 <= x["slot"] <= S1 and x.get("err") is None]
    before = r[-1]["signature"]
    if r[-1]["slot"] < S0 or pages > 60:
        break
done = set()
if os.path.exists(OUT):
    done = {json.loads(l)["sig"] for l in open(OUT)}
todo = [x for x in sigs if x["signature"] not in done]
print(f"pages {pages} ok sigs {len(sigs)} todo {len(todo)}", flush=True)
lk = threading.Lock()
fh = open(OUT, "a")


def work(x):
    t = rpc("getTransaction", [x["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    rec = {"sig": x["signature"], "slot": x["slot"]}
    if isinstance(t, dict) and t.get("meta"):
        tr, _ = events(t["meta"].get("logMessages"))
        rec["buys"] = [[e["mint"], e["sol"], e["tok"]] for e in tr if e.get("buy") and e.get("user") == W4]
        rec["sells"] = [[e["mint"], e["sol"], e["tok"]] for e in tr if not e.get("buy") and e.get("user") == W4]
    with lk:
        fh.write(json.dumps(rec) + "\n")
        fh.flush()


with ThreadPoolExecutor(6) as ex:
    list(ex.map(work, todo))
print("FINISHED", stats, flush=True)
