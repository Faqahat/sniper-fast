# READ-ONLY RPC helper for the CWiNFA study. The owner's RPC URL is read from ~/.config/sniper/ck_rpc_url and never printed.
# A process-wide rate limiter keeps this study at <= RATE requests/s on the shared RPC (default 4).
import os, json, time, threading, urllib.request
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
PUB = "https://api.mainnet-beta.solana.com"
W = "CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J"
RATE = float(os.environ.get("RPC_RATE", "4"))
_lock = threading.Lock(); _last = [0.0]; _plock = threading.Lock(); _plast = [0.0]
def _wait(lock, last, gap):
    with lock:
        w = last[0] + gap - time.time()
        if w > 0: time.sleep(w)
        last[0] = time.time()
def post(m, p, ep=None, timeout=60):
    if ep is None or ep == EP: _wait(_lock, _last, 1.0 / RATE)
    else: _wait(_plock, _plast, 0.6)          # public endpoint: ~1.6 req/s
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
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"; B58I = {c: i for i, c in enumerate(B58)}
def b58enc(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
def b58dec(s):
    n = 0
    for c in s: n = n * 58 + B58I[c]
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\x00" * (len(s) - len(s.lstrip("1"))) + b
