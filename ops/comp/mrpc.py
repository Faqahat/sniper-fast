# READ-ONLY multi-endpoint JSON-RPC client: round-robin over Constant-K / RMR / Shyft with per-endpoint pacing and 429 backoff.
# Never prints URLs (they carry keys).
import json, os, time, threading, random, urllib.request, urllib.error

EPS = []
for name, url in (("ck", "https://rpc-frankfurt.constant-k.com/?api-key=" + os.environ.get("CONSTANTK_TOKEN", "") if os.environ.get("CONSTANTK_TOKEN") else ""),
                  ("rmr", os.environ.get("RMR_RPC_URL", "")), ("shyft", os.environ.get("SHYFT_RPC_URL", ""))):
    if url:
        rps = float(os.environ.get("EP_RPS_" + name.upper(), os.environ.get("EP_RPS", "12")))
        EPS.append({"name": name, "url": url, "gap": 1.0 / rps, "base": 1.0 / rps, "next": 0.0, "lock": threading.Lock(),
                    "ok": 0, "r429": 0, "err": 0, "cool": 0.0})
_rr = [0]
_rrl = threading.Lock()


def _pick():
    with _rrl:
        now = time.time()
        cands = [e for e in EPS if e["cool"] <= now] or EPS
        return min(cands, key=lambda e: e["next"])


def _pace(ep):
    with ep["lock"]:
        now = time.time()
        t = max(now, ep["next"])
        ep["next"] = t + ep["gap"]
    d = t - time.time()
    if d > 0:
        time.sleep(d)


def rpc(m, p, tries=10, timeout=45):
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode()
    last = None
    for i in range(tries):
        ep = _pick()
        _pace(ep)
        try:
            req = urllib.request.Request(ep["url"], data=data, headers={"content-type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                r = json.loads(resp.read())
            if "error" in r:
                code = r["error"].get("code")
                if code in (-32007, -32009, -32004) and i >= 1:
                    return {"__err": code}
                last = r["error"]; ep["err"] += 1
                time.sleep(0.3 * (i + 1))
                continue
            ep["ok"] += 1
            if ep["gap"] > ep["base"]:
                with ep["lock"]:
                    ep["gap"] = max(ep["base"], ep["gap"] * 0.95)
            res = r.get("result")
            if res is None and m == "getTransaction" and i < 3:
                time.sleep(0.2); continue  # some endpoints lag; retry elsewhere
            return res
        except urllib.error.HTTPError as ex:
            last = ex
            if ex.code == 429:
                ep["r429"] += 1
                with ep["lock"]:
                    ep["gap"] = min(0.5, ep["gap"] * 1.2)
                    ep["cool"] = time.time() + 0.5 + random.random()
                    ep["next"] = min(ep["next"], time.time() + 1.0)
                time.sleep(0.2 + random.random() * 0.3)
            else:
                ep["err"] += 1
                time.sleep(0.5 * (i + 1))
        except Exception as ex:
            last = ex; ep["err"] += 1
            time.sleep(0.5 * (i + 1))
    return {"__err": str(last)[:200]}


def stats():
    return " ".join(f"{e['name']}:ok{e['ok']}/429:{e['r429']}/err{e['err']}/gap{e['gap']:.3f}" for e in EPS)
