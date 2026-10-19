# RPC wrapper for /root/strat: <=4 concurrent, backoff on 429/errors. READ-ONLY.
import json, os, time, threading, urllib.request, urllib.error, random
TOK = os.environ.get("CONSTANTK_TOKEN", "")
RPC = f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
SEM = threading.Semaphore(int(os.environ.get("STRAT_CONC", "4")))
stats = {"calls": 0, "429": 0, "err": 0}
def rpc(m, p, tries=8, timeout=60):
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode()
    last = None
    for i in range(tries):
        with SEM:
            try:
                stats["calls"] += 1
                req = urllib.request.Request(RPC, data=data, headers={"content-type": "application/json"})
                r = json.load(urllib.request.urlopen(req, timeout=timeout))
            except urllib.error.HTTPError as ex:
                last = ex
                if ex.code == 429:
                    stats["429"] += 1
                    r = None
                else:
                    stats["err"] += 1
                    r = None
            except Exception as ex:
                last = ex; stats["err"] += 1; r = None
        if r is None:
            time.sleep(min(10, 0.5 * 2 ** i) * (0.5 + random.random()))
            continue
        if "error" in r:
            code = r["error"].get("code")
            if code in (-32007, -32009, -32004, -32020) and i >= 1:
                return {"__err": code}
            last = r["error"]
            time.sleep(min(10, 0.5 * 2 ** i))
            continue
        return r.get("result")
    return {"__err": str(last)[:200]}
