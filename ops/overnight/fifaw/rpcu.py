# shared RPC helper (READ-ONLY). The owner's RPC URL is read from ~/.config/sniper/ck_rpc_url and never printed.
import os, json, time, urllib.request
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
PUB = "https://api.mainnet-beta.solana.com"
W = "FiFawHqxeTVBhv6YbqbLwDVuvokRpPUM1bNwAyxhGc6W"
def post(m, p, ep=None, timeout=60):
    return json.load(urllib.request.urlopen(urllib.request.Request(ep or EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=timeout))
def rpc(m, p, ep=None, tries=6):
    last = None
    for i in range(tries):
        try:
            r = post(m, p, ep)
            if "result" in r: return r["result"]
            last = r.get("error")
        except Exception as e: last = type(e).__name__
        time.sleep(0.5 + i)
    raise RuntimeError(f"rpc {m} failed: {str(last)[:200]}")
