"""Gentle PUBLIC-RPC client (read-only). Never the Constant-K key. <= ~2.5 req/s, retry with backoff on 429/5xx/timeouts."""
import json, time, urllib.request, urllib.error
URL = "https://api.mainnet-beta.solana.com"
_last = [0.0]
MIN_GAP = 1.2      # the public RPC answers 429 'too many requests for a specific RPC call' above ~0.5 getTransaction/s


def call(method, params, tries=8):
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    back = 2.0
    for t in range(tries):
        w = _last[0] + MIN_GAP - time.time()
        if w > 0: time.sleep(w)
        _last[0] = time.time()
        try:
            j = json.load(urllib.request.urlopen(urllib.request.Request(URL, data=data, headers={"content-type": "application/json"}), timeout=60))
            if "error" in j:
                msg = str(j["error"])[:200]
                if "429" in msg or "rate" in msg.lower() or j["error"].get("code") in (-32005, -32429):
                    time.sleep(back); back = min(back * 2, 60); continue
                return j
            return j
        except urllib.error.HTTPError as e:
            time.sleep(back); back = min(back * 2, 60)
        except Exception as e:
            time.sleep(back); back = min(back * 2, 60)
    raise RuntimeError(f"rpc {method} failed after {tries}")
