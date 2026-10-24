#!/usr/bin/env python3
# READ-ONLY, RESUMABLE: fetch every tx in sigs_<w6>.json (owner-RPC range by default) into txc_<w6>/<sig>.json (jsonParsed, v1 ok).
# usage: python3 -I fetch.py [wallet] [--all]   (--all also tries public mainnet-beta for older sigs, slow)
import sys, os, json, time, threading, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import rpcu
W = next((a for a in sys.argv[1:] if not a.startswith("--")), rpcu.W); ALL = "--all" in sys.argv
HERE = os.path.dirname(os.path.abspath(__file__)); C = os.path.join(HERE, f"txc_{W[:6]}"); os.makedirs(C, exist_ok=True)
S = json.load(open(os.path.join(HERE, f"sigs_{W[:6]}.json")))
MINSLOT = int(os.environ.get("MINSLOT", "0"))
todo = [s["signature"] for s in S if (ALL or s["src"] == "owner") and s["slot"] >= MINSLOT and not os.path.exists(os.path.join(C, s["signature"] + ".json"))]
print(f"{len(S)} sigs; to fetch {len(todo)}", flush=True)
def fast(sig):
    for i in range(4):
        try:
            r = rpcu.post("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}]).get("result")
            if r: json.dump(r, open(os.path.join(C, sig + ".json"), "w")); return True
            return False
        except Exception: time.sleep(1 + i)
    return False
with cf.ThreadPoolExecutor(12) as ex: ok = sum(ex.map(fast, todo))
left = [s for s in todo if not os.path.exists(os.path.join(C, s + ".json"))]
print(f"owner RPC gave {ok}; still missing {len(left)}", flush=True)
if ALL and left:
    lock = threading.Lock(); last = [0.0]; done = [0]
    def slow(sig):
        for i in range(8):
            with lock:
                w = last[0] + 0.29 - time.time()
                if w > 0: time.sleep(w)
                last[0] = time.time()
            try:
                r = rpcu.post("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}], ep=rpcu.PUB)
                if r.get("result"): json.dump(r["result"], open(os.path.join(C, sig + ".json"), "w")); break
            except Exception: time.sleep(2 + 2 * i)
        with lock:
            done[0] += 1
            if done[0] % 250 == 0: print(f"public: {done[0]} / {len(left)}", flush=True)
    with cf.ThreadPoolExecutor(4) as ex: list(ex.map(slow, left))
print("done", flush=True)
