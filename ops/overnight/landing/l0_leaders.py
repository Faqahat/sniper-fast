#!/usr/bin/env python3
# LANDING-PATH STUDY, step 0 (READ-ONLY RPC, ~90 requests, <= 4 req/s): slot leaders for both runs' slot ranges
# (getSlotLeaders, 5000 slots per call) + one getClusterNodes (clientId per validator identity).
# The RPC URL is read from ~/.config/sniper/ck_rpc_url and is never printed or written anywhere.
# usage: python3 -I l0_leaders.py <out_dir> <lo_slot> <hi_slot> [<lo_slot> <hi_slot> ...]
import sys, os, json, time, urllib.request

OUT = sys.argv[1]
RANGES = [(int(sys.argv[k]), int(sys.argv[k + 1])) for k in range(2, len(sys.argv), 2)]
URL = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
_last = [0.0]


def rpc(method, params, tries=5):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for k in range(tries):
        w = _last[0] + 0.25 - time.time()
        if w > 0: time.sleep(w)
        _last[0] = time.time()
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(URL, data=body, headers={"content-type": "application/json"}), timeout=60))
            if "error" in r:
                print(method, "rpc error code", r["error"].get("code"), str(r["error"].get("message"))[:120], flush=True)
                time.sleep(1 + k); continue
            return r.get("result")
        except Exception as e:
            print(method, "exception", type(e).__name__, flush=True)   # no URL in the message
            time.sleep(1 + 2 * k)
    return None


os.makedirs(OUT, exist_ok=True)
lf = os.path.join(OUT, "leaders.json")
leaders = json.load(open(lf)) if os.path.exists(lf) else {}
for lo, hi in RANGES:
    s = lo
    while s <= hi:
        if all(str(x) in leaders for x in range(s, min(hi, s + 4999) + 1)):
            s += 5000; continue
        r = rpc("getSlotLeaders", [s, 5000])
        if isinstance(r, list):
            for k, l in enumerate(r): leaders[str(s + k)] = l
        else:
            print("no leaders for", s, flush=True)
        s += 5000
    json.dump(leaders, open(lf, "w"))
print("leaders:", len(leaders), flush=True)
cn = rpc("getClusterNodes", [])
if isinstance(cn, list):
    slim = {x["pubkey"]: {"clientId": x.get("clientId"), "version": x.get("version"), "tpuQuic": x.get("tpuQuic"), "gossip": x.get("gossip")} for x in cn}
    json.dump({"t": time.time(), "nodes": slim}, open(os.path.join(OUT, "clusternodes_now.json"), "w"))
    print("cluster nodes:", len(slim), flush=True)
