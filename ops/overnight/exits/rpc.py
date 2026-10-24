#!/usr/bin/env python3
# READ-ONLY helper: rate-limited JSON-RPC to the owner's Constant-K endpoint (URL read from ~/.config/sniper/ck_rpc_url, never printed).
import os, json, time, threading, urllib.request
_URL = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
_lk = threading.Lock(); _next = [0.0]; RPS = 8.0
def rpc(method, params, tries=6, timeout=60):
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for i in range(tries):
        with _lk:
            now = time.time(); wait = _next[0] - now
            _next[0] = max(now, _next[0]) + 1.0 / RPS
        if wait > 0: time.sleep(wait)
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(_URL, data=data, headers={"content-type": "application/json"}), timeout=timeout))
            if "result" in r: return r["result"]
            if "error" in r and i >= 2: return None
        except Exception:
            pass
        time.sleep(0.5 * (i + 1))
    return None
def get_tx(sig):
    return rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
