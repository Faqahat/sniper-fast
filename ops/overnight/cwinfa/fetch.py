#!/usr/bin/env python3
# READ-ONLY, RESUMABLE: every signature of CWiNFA the owner's RPC still has (paginated until it returns nothing), then every
# transaction (jsonParsed, v1-capable) cached to txc/<sig>.json. Rate-limited by rpcw (<= 4 req/s on the shared RPC).
# usage: python3 -I fetch.py
import os, sys, json, time, concurrent.futures as cf
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import rpcw
W = rpcw.W; C = os.path.join(HERE, "txc"); os.makedirs(C, exist_ok=True)
SIGS = os.path.join(HERE, "sigs_CWiNFA.json")
sigs = json.load(open(SIGS)) if os.path.exists(SIGS) else []
have_sig = {s["signature"] for s in sigs}
# 1) newest first: pull anything newer than what we have, then page back until the RPC runs out of history
new, before = [], None
while True:
    p = {"limit": 1000}
    if before: p["before"] = before
    try: r = rpcw.rpc("getSignaturesForAddress", [W, p])
    except RuntimeError as e: print("sig page error (end of history?)", e, flush=True); break
    if not r: break
    fresh = [s for s in r if s["signature"] not in have_sig]
    new += fresh; before = r[-1]["signature"]
    print(f"  page: {len(r)} sigs, slots {r[0]['slot']}..{r[-1]['slot']}, new {len(fresh)}", flush=True)
    if len(r) < 1000: break
    if not fresh and sigs: # reached what we already have; continue paging from our oldest
        before = min(sigs, key=lambda s: s["slot"])["signature"]
        while True:
            p = {"limit": 1000, "before": before}
            try: r = rpcw.rpc("getSignaturesForAddress", [W, p])
            except RuntimeError as e: print("sig page error", e, flush=True); r = []
            if not r: break
            new += [s for s in r if s["signature"] not in have_sig]; before = r[-1]["signature"]
            print(f"  older page: {len(r)} sigs, slots {r[0]['slot']}..{r[-1]['slot']}", flush=True)
            if len(r) < 1000: break
        break
sigs = sorted({s["signature"]: s for s in sigs + new}.values(), key=lambda s: (s["slot"], s["signature"]))
json.dump(sigs, open(SIGS, "w"))
print(f"{W[:8]}: {len(sigs)} sigs (failed {sum(1 for s in sigs if s.get('err') is not None)}), slots {sigs[0]['slot']}..{sigs[-1]['slot']}", flush=True)
# 2) transactions
have = lambda s: os.path.exists(os.path.join(C, s + ".json"))
todo = [s["signature"] for s in sigs if not have(s["signature"])]
print(f"  to fetch {len(todo)}", flush=True)
done = [0]; miss = []
def one(sig):
    try:
        t = rpcw.rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    except RuntimeError: t = None
    if t: json.dump(t, open(os.path.join(C, sig + ".json"), "w"))
    else: miss.append(sig)
    done[0] += 1
    if done[0] % 250 == 0: print(f"    {done[0]} / {len(todo)}", flush=True)
with cf.ThreadPoolExecutor(int(os.environ.get("THREADS", "8"))) as ex: list(ex.map(one, todo))
print(f"  fetched; missing {len(miss)}", flush=True)
json.dump(miss, open(os.path.join(HERE, "missing.json"), "w"))
print("FETCH DONE", time.strftime("%H:%M:%S", time.gmtime()), flush=True)
