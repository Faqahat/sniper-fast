#!/usr/bin/env python3
# READ-ONLY helper: rate-limited JSON-RPC to the owner's Constant-K endpoint (URL read from ~/.config/sniper/ck_rpc_url,
# never printed). Shared RPC with another study -> global cap ~4 req/s across all threads of this process.
# Optional cross-process cap: a lock file in this folder spaces requests of every process that imports this module.
import os, json, time, threading, urllib.request, fcntl
_URL = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
PUB = "https://api.mainnet-beta.solana.com"
_lk = threading.Lock(); RPS = float(os.environ.get("DK_RPS", "4.0"))
_TS = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".rpc_pace")
def _pace():
    # cross-process pacing via a tiny file holding the next allowed time
    with _lk:
        fd = os.open(_TS, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            raw = os.read(fd, 64); nxt = float(raw or b"0")
            now = time.time(); wait = nxt - now
            os.lseek(fd, 0, 0); os.ftruncate(fd, 0); os.write(fd, repr(max(now, nxt) + 1.0 / RPS).encode())
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd)
    if wait > 0: time.sleep(wait)
def rpc(method, params, tries=6, timeout=60, public=False):
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for i in range(tries):
        if not public: _pace()
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(PUB if public else _URL, data=data, headers={"content-type": "application/json"}), timeout=timeout))
            if "result" in r: return r["result"]
            if "error" in r:
                msg = str(r["error"])[:200]
                if i >= 2: return {"__error__": msg}
        except Exception as e:
            pass
        time.sleep(0.6 * (i + 1))
    return None
def get_tx(sig, public=False):
    r = rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}], public=public)
    return r if isinstance(r, dict) and "__error__" not in r else None
