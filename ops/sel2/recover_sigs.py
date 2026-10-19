import os, json, time, urllib.request, urllib.error, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

RPC = "https://rpc-frankfurt.constant-k.com/?api-key=" + os.environ["CONSTANTK_TOKEN"]


def rpc(method, params, tries=7):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    last = None
    for t in range(tries):
        try:
            req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=40) as r:
                j = json.loads(r.read())
            if "error" in j:
                last = j["error"]
                time.sleep(0.3 * (t + 1))
                continue
            return j.get("result")
        except urllib.error.HTTPError as e:
            last = e
            time.sleep(0.8 + 0.6 * t if getattr(e, "code", 0) == 429 else 0.4 * (t + 1))
        except Exception as e:
            last = e
            time.sleep(0.4 * (t + 1))
    return None


def oldest_sig(mint, max_pages=40):
    before = None
    last = None
    pages = 0
    while pages < max_pages:
        p = [mint, {"limit": 1000}]
        if before:
            p[1]["before"] = before
        r = rpc("getSignaturesForAddress", p)
        pages += 1
        if not r:
            break
        last = r[-1]
        if len(r) < 1000:
            # reached oldest page
            return last["signature"], False
        before = r[-1]["signature"]
    # capped out
    return (last["signature"] if last else None), True


def work(mint):
    sig, capped = oldest_sig(mint)
    return mint, {"create_sig": sig, "deep_capped": capped}


def main():
    mints = json.load(open(sys.argv[1]))
    if isinstance(mints, dict):
        mints = list(mints.keys())
    outpath = sys.argv[2]
    cache = {}
    if os.path.exists(outpath):
        try:
            cache = json.load(open(outpath))
        except Exception:
            cache = {}
    todo = [m for m in mints if m not in cache or not cache[m].get("create_sig")]
    print(f"recover: total={len(mints)} todo={len(todo)}", file=sys.stderr, flush=True)
    out = dict(cache)
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(work, m): m for m in todo}
        done = 0
        for f in as_completed(futs):
            m, r = f.result()
            out[m] = r
            done += 1
            if done % 25 == 0:
                json.dump(out, open(outpath, "w"))
                print(f"  {done}/{len(todo)}", file=sys.stderr, flush=True)
    json.dump(out, open(outpath, "w"))
    got = sum(1 for v in out.values() if v.get("create_sig"))
    print(f"recover DONE {outpath} with_sig={got}/{len(out)}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
