#!/usr/bin/env python3
# READ-ONLY JSON-RPC helper for the q9z study. The owner's RPC URL is read from ~/.config/sniper/ck_rpc_url and never printed.
# Global pacing: at most RATE requests/s across all threads of this process (shared RPC: keep <= 4 req/s).
import os, json, time, threading, urllib.request
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
RATE = float(os.environ.get("Q9Z_RATE", "3.8"))
_lock = threading.Lock(); _next = [0.0]
def _pace():
    with _lock:
        now = time.time(); w = _next[0] - now
        _next[0] = max(now, _next[0]) + 1.0 / RATE
    if w > 0: time.sleep(w)
def rpc(method, params, tries=6, timeout=60):
    for i in range(tries):
        _pace()
        try:
            req = urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
                                         headers={"content-type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=timeout))
            if "result" in r: return r["result"]
            err = r.get("error") or {}
            if err.get("code") in (-32009, -32004, -32007, -32011): return None   # slot skipped / not available / pruned
        except Exception as e:
            pass
        time.sleep(1.0 + i)
    return None
