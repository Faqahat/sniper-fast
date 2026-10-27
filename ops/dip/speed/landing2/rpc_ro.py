#!/usr/bin/env python3
# Read-only JSON-RPC helper for this study: CK URL from ~/.config/sniper/ck_rpc_url (never printed), <= 4 req/s, retries,
# on-disk cache for getTransaction (/home/moiz/sniper-data/landing2/txcache/<sig>.json).
import os, json, time, urllib.request, threading
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
CACHE = "/home/moiz/sniper-data/landing2/txcache"; os.makedirs(CACHE, exist_ok=True)
_lock = threading.Lock(); _last = [0.0]; MIN_GAP = 0.25
def _pace():
    with _lock:
        now = time.time(); w = _last[0] + MIN_GAP - now
        if w > 0: time.sleep(w)
        _last[0] = time.time()
def rpc(method, params, timeout=60):
    for k in range(5):
        _pace()
        try:
            req = urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
                                         headers={"content-type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=timeout))
            if "result" in r: return r["result"]
            err = r.get("error") or {}
            if err.get("code") in (-32009, -32007, -32004): return None    # slot skipped / not available / pruned
        except Exception as e:
            pass
        time.sleep(1.0 + k)
    return None
def get_tx(sig):
    p = os.path.join(CACHE, sig + ".json")
    if os.path.exists(p):
        try: return json.load(open(p))
        except Exception: pass
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    if t is not None: json.dump(t, open(p, "w"))
    return t
