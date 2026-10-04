"""Optional chain fetches (getBlock, getTransaction, getSignaturesForAddress) with a cache in <seg>/chain-cache/.

- The RPC URL is read only from the environment variable named by `--rpc-url-env`. The toolkit never opens `.env`
  files and never writes the URL anywhere (only the host appears in reports).
- `--offline` forbids every network call; callers then mark chain-dependent sections incomplete.
- Calls are rate limited (default 5/s) and cached by (method, key), so a re-run is identical and free.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request


class Offline(Exception):
    pass


class Chain:
    def __init__(self, cache_dir: str | None, rpc_url_env: str | None = None, offline: bool = True, max_rps: float = 5.0):
        self.cache_dir = cache_dir
        self.offline = offline or not rpc_url_env
        self.env = rpc_url_env
        self.min_gap = 1.0 / max_rps if max_rps > 0 else 0
        self._last = 0.0
        self.calls = 0
        self.cache_hits = 0

    @property
    def host(self) -> str | None:
        if self.offline or not self.env:
            return None
        url = os.environ.get(self.env) or ""
        return urllib.parse.urlparse(url).hostname

    def _cache_path(self, method: str, key: str) -> str | None:
        if not self.cache_dir:
            return None
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(key))
        return os.path.join(self.cache_dir, f"{method}-{safe}.json")

    def call(self, method: str, params: list, key: str):
        p = self._cache_path(method, key)
        if p and os.path.exists(p):
            self.cache_hits += 1
            with open(p) as f:
                return json.load(f)
        if self.offline:
            raise Offline(f"{method}({key}) not cached and network calls are off (--offline or no --rpc-url-env)")
        url = os.environ.get(self.env or "")
        if not url:
            raise Offline(f"environment variable {self.env} is empty")
        wait = self._last + self.min_gap - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            res = json.loads(r.read())
        self._last = time.monotonic()
        self.calls += 1
        if "error" in res:
            raise RuntimeError(f"{method}: {res['error']}")
        out = res.get("result")
        if p:
            os.makedirs(self.cache_dir, exist_ok=True)
            tmp = p + ".tmp"
            with open(tmp, "w") as f:
                json.dump(out, f, sort_keys=True)
            os.replace(tmp, p)
        return out

    def get_block(self, slot: int, full: bool = True):
        opts = {"encoding": "json", "maxSupportedTransactionVersion": 0, "rewards": False,
                "transactionDetails": "full" if full else "signatures", "commitment": "confirmed"}
        return self.call("getBlock", [slot, opts], f"{slot}-{'full' if full else 'sigs'}")

    def get_transaction(self, sig: str):
        return self.call("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0,
                                                  "commitment": "confirmed"}], sig)
