# READ-ONLY RPC helper with a process-wide rate limiter and patient 429 backoff.
import json, os, time, threading, urllib.request, urllib.error, random

TOK = os.environ.get("CONSTANTK_TOKEN", "")
URL = f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
RPS = float(os.environ.get("NOB_RPS", "20"))
_lock = threading.Lock()
_next = [0.0]
stats = {"calls": 0, "r429": 0, "err": 0}


def _wait():
    with _lock:
        now = time.time()
        t = max(now, _next[0])
        _next[0] = t + 1.0 / RPS
    d = t - time.time()
    if d > 0:
        time.sleep(d)


def rpc(m, p, tries=14, timeout=60):
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode()
    last = None
    for i in range(tries):
        _wait()
        stats["calls"] += 1
        try:
            req = urllib.request.Request(URL, data=data, headers={"content-type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=timeout))
            if "error" in r:
                code = r["error"].get("code")
                if code in (-32007, -32009, -32004, -32020) and i >= 1:
                    return {"__err": code, "msg": str(r["error"])[:150]}
                last = r["error"]
                time.sleep(0.5 * (i + 1))
                continue
            return r.get("result")
        except urllib.error.HTTPError as ex:
            last = ex
            if ex.code == 429:
                stats["r429"] += 1
                time.sleep(min(8, 0.4 * 2 ** min(i, 4)) + random.random() * 0.5)
            else:
                time.sleep(0.5 * (i + 1))
        except Exception as ex:
            last = ex
            stats["err"] += 1
            time.sleep(0.5 * (i + 1))
    return {"__err": str(last)[:200]}
