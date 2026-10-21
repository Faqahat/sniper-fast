# READ-ONLY (host; public RPC): getSignaturesForAddress for many wallets back to <hours> ago (one request at a time).
# publicnode first (~23 h of history), then api.mainnet-beta for older pages. Skips wallets already fetched.
# usage: python3 -I sigs_multi.py <wallets.txt> <hours> <out_dir>     (writes <out_dir>/<wallet>.sigs.json)
import sys, os, json, time, urllib.request
WF, H, OUT = sys.argv[1], float(sys.argv[2]), sys.argv[3]
EPS = ["https://solana-rpc.publicnode.com", "https://api.mainnet-beta.solana.com"]
MAXSIG = int(os.environ.get("MAXSIG", "60000"))


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
for W in [l.split()[0] for l in open(WF) if l.strip() and not l.startswith("#")]:
    fn = os.path.join(OUT, W + ".sigs.json")
    if os.path.exists(fn): continue
    out = []; before = None; ep_i = 0
    while True:
        p = {"limit": 1000}
        if before: p["before"] = before
        res = rpc(EPS[ep_i], "getSignaturesForAddress", [W, p])
        if not res:
            if ep_i == 0: ep_i = 1; continue
            break
        out += [dict(sig=r["signature"], slot=r["slot"], bt=r.get("blockTime"), err=r.get("err") is not None) for r in res]
        before = res[-1]["signature"]; bt = res[-1].get("blockTime") or 0
        if bt and bt < stop: break
        if len(out) >= MAXSIG: break
        if len(res) < 1000:
            if ep_i == 0: ep_i = 1; continue
            break
    out = [r for r in out if not r["bt"] or r["bt"] >= stop]
    json.dump(out, open(fn, "w"))
    bts = [r["bt"] for r in out if r["bt"]]
    span = (max(bts) - min(bts)) / 3600 if bts else 0
    print(f"{W[:12]} sigs {len(out)} ok {sum(not r['err'] for r in out)} failed {sum(r['err'] for r in out)} span {span:.1f} h"
          f" oldest {time.strftime('%m-%d %H:%M', time.gmtime(min(bts))) if bts else '-'}", flush=True)
