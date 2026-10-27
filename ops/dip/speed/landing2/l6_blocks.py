#!/usr/bin/env python3
# LANDING2 step 6 (read-only RPC, <= 4 req/s): the REAL size (tx count incl. votes-free? -> all signatures) of every block that holds a
# fired dump, the next 2 blocks, and every block where one of our buys landed. getBlock(transactionDetails=signatures).
# URL from ~/.config/sniper/ck_rpc_url (never printed). Output: OUT/block_sizes.json {slot: n_txs or null}
import json, os, time, urllib.request

OUT = "/home/moiz/sniper-data/landing2"
URL = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()


def get_block(s):
    p = [s, {"transactionDetails": "signatures", "rewards": False, "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}]
    req = urllib.request.Request(URL, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getBlock", "params": p}).encode(),
                                 headers={"content-type": "application/json"})
    for k in range(3):
        try:
            r = json.load(urllib.request.urlopen(req, timeout=30))
            if r.get("result"): return len(r["result"]["signatures"])
            if r.get("error"): return None if r["error"].get("code") in (-32007, -32009) else "err"
        except Exception:
            time.sleep(1.0)
    return "err"


def main():
    fires = json.load(open(f"{OUT}/fires_engine.json"))
    want = set()
    for a in fires:
        for d in range(0, 3): want.add(a["dump_slot"] + d)
        for k in ("land", "fail"):
            if a.get(k): want.add(a[k]["slot"])
        if a["timing"].get("clock2"):
            c = a["timing"]["clock2"]
            if c.get("buy_slot"): want.add(c["buy_slot"])
    fn = f"{OUT}/block_sizes.json"
    have = json.load(open(fn)) if os.path.exists(fn) else {}
    todo = sorted(s for s in want if str(s) not in have or have[str(s)] == "err")
    print("blocks wanted", len(want), "to fetch", len(todo), flush=True)
    t0 = time.time()
    for k, s in enumerate(todo):
        have[str(s)] = get_block(s)
        time.sleep(0.25)
        if k % 100 == 99:
            json.dump(have, open(fn, "w")); print(k + 1, f"{time.time() - t0:.0f}s", flush=True)
    json.dump(have, open(fn, "w"))
    print("done", len(have), "skipped/null", sum(1 for v in have.values() if v is None), "err", sum(1 for v in have.values() if v == "err"))


if __name__ == "__main__":
    main()
