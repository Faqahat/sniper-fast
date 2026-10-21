# READ-ONLY (host; public RPC): page getSignaturesForAddress for a wallet back to <hours> ago.
# publicnode first (~23 h of history), then api.mainnet-beta for older pages.
# usage: python3 sigs.py <wallet> <hours> <out.json>
import sys, json, time, urllib.request
W, H, OUT = sys.argv[1], float(sys.argv[2]), sys.argv[3]
EPS = ["https://solana-rpc.publicnode.com", "https://api.mainnet-beta.solana.com"]


def rpc(ep, meth, params, tries=10):
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": meth, "params": params}).encode()
    for i in range(tries):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(ep, data=data, headers={"content-type": "application/json", "user-agent": "curl/8.5.0"}), timeout=60))
            if "error" in r: time.sleep(2 + i); continue
            return r["result"]
        except Exception:
            time.sleep(2 + 2 * i)
    return None


stop = time.time() - H * 3600
out = []; before = None; ep_i = 0
while True:
    p = {"limit": 1000}
    if before: p["before"] = before
    res = rpc(EPS[ep_i], "getSignaturesForAddress", [W, p])
    if not res:
        if ep_i == 0: ep_i = 1; print("switch to mainnet-beta", flush=True); continue
        break
    out += [dict(sig=r["signature"], slot=r["slot"], bt=r.get("blockTime"), err=r.get("err") is not None) for r in res]
    before = res[-1]["signature"]; bt = res[-1].get("blockTime") or 0
    print(f"{len(out)} sigs, oldest {time.strftime('%m-%d %H:%M', time.gmtime(bt))} via {EPS[ep_i][8:20]}", flush=True)
    if bt and bt < stop: break
    if len(res) < 1000:
        if ep_i == 0: ep_i = 1; print("publicnode history ended; switch to mainnet-beta", flush=True); continue
        break
json.dump(out, open(OUT, "w"))
print("DONE", len(out), "ok", sum(not r["err"] for r in out))
