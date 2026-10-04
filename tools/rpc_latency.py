#!/usr/bin/env python3
"""RPC latency check (read-only): warm keep-alive latency per method and a cold connection breakdown, per provider.

usage (on the bot host, with the bot's .env loaded into the environment, never printed):
    set -a; . /root/arb-lab/.env; set +a; python3 tools/rpc_latency.py --seed data/seed-pools-w4.csv --out runs/rpc-latency.json

Providers: haan (https://rpc.haandigital.eu/, Bearer HAAN_API_KEY), shyft (SHYFT_RPC_URL), public (api.mainnet-beta).
URLs and keys are never printed; output names providers only. Requests are sequential with a pause (default 0.2 s),
so the load is about 5 requests/s per provider.
"""
import argparse, csv, http.client, json, os, socket, ssl, statistics, sys, time, urllib.parse

def providers():
    out = []
    if os.environ.get("HAAN_API_KEY"):
        out.append(("haan", "https://rpc.haandigital.eu/", {"Authorization": "Bearer " + os.environ["HAAN_API_KEY"]}))
    if os.environ.get("SHYFT_RPC_URL"):
        out.append(("shyft", os.environ["SHYFT_RPC_URL"], {}))
    out.append(("public", "https://api.mainnet-beta.solana.com", {}))
    return out

class Conn:
    """one persistent HTTPS connection (HTTP/1.1 keep-alive); reconnects on error"""
    def __init__(self, url, headers):
        u = urllib.parse.urlsplit(url)
        self.host, self.port = u.hostname, u.port or 443
        self.path = (u.path or "/") + (("?" + u.query) if u.query else "")
        self.headers = {"content-type": "application/json", **headers}
        self.c = None
    def call(self, method, params, timeout=10):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        for attempt in range(2):
            try:
                if self.c is None:
                    self.c = http.client.HTTPSConnection(self.host, self.port, timeout=timeout)
                t0 = time.perf_counter()
                self.c.request("POST", self.path, body=body, headers=self.headers)
                r = self.c.getresponse(); data = r.read()
                dt = (time.perf_counter() - t0) * 1000
                ok = r.status == 200
                err = None
                if ok:
                    j = json.loads(data)
                    if "error" in j: ok, err = False, str(j["error"].get("code"))
                else:
                    err = f"http {r.status}"
                return dt, ok, err, len(data), (json.loads(data).get("result") if ok else None)
            except Exception as e:
                self.c = None
                if attempt: return None, False, type(e).__name__, 0, None
        return None, False, "unknown", 0, None

def cold(url, headers):
    """one fresh connection: DNS, TCP connect, TLS handshake, time to first byte, total (ms)"""
    u = urllib.parse.urlsplit(url); host, port = u.hostname, u.port or 443
    path = (u.path or "/") + (("?" + u.query) if u.query else "")
    t0 = time.perf_counter(); ip = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)[0][4][0]; t1 = time.perf_counter()
    s = socket.create_connection((ip, port), timeout=10); t2 = time.perf_counter()
    ctx = ssl.create_default_context(); ss = ctx.wrap_socket(s, server_hostname=host); t3 = time.perf_counter()
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getSlot", "params": []}).encode()
    hdr = "".join(f"{k}: {v}\r\n" for k, v in {"Host": host, "content-type": "application/json", "content-length": str(len(body)), **headers}.items())
    ss.sendall(f"POST {path} HTTP/1.1\r\n{hdr}\r\n".encode() + body); ss.recv(1); t4 = time.perf_counter()
    ss.close()
    return {"ip": ip, "dns_ms": (t1 - t0) * 1e3, "tcp_ms": (t2 - t1) * 1e3, "tls_ms": (t3 - t2) * 1e3, "ttfb_ms": (t4 - t3) * 1e3, "total_ms": (t4 - t0) * 1e3}

def pct(v, p):
    v = sorted(v); return round(v[min(len(v) - 1, int(len(v) * p))], 3) if v else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="data/seed-pools-w4.csv")
    ap.add_argument("--n", type=int, default=60, help="calls per method per provider")
    ap.add_argument("--pause", type=float, default=0.2)
    ap.add_argument("--cold", type=int, default=5)
    ap.add_argument("--out", default="runs/rpc-latency.json")
    a = ap.parse_args()
    pools = [r["pool"] for r in csv.DictReader(open(a.seed))][:200]
    out = {"t_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "host": socket.gethostname(), "n": a.n, "providers": {}}
    for name, url, headers in providers():
        res = {"cold": [], "methods": {}}
        for _ in range(a.cold):
            try: res["cold"].append(cold(url, headers))
            except Exception as e: res["cold"].append({"error": type(e).__name__})
            time.sleep(a.pause)
        c = Conn(url, headers)
        c.call("getSlot", [])  # warm the connection
        sig = None
        dt, ok, err, n, r = c.call("getSignaturesForAddress", [pools[0], {"limit": 5}])
        if ok and r: sig = r[0]["signature"]
        tests = [
            ("getSlot", []),
            ("getLatestBlockhash", [{"commitment": "confirmed"}]),
            ("getAccountInfo", [pools[1], {"encoding": "base64"}]),
            ("getMultipleAccounts_10", [pools[:10], {"encoding": "base64"}]),
            ("getMultipleAccounts_100", [pools[:100], {"encoding": "base64"}]),
        ]
        if sig:
            tests.append(("getSignatureStatuses", [[sig], {"searchTransactionHistory": False}]))
            tests.append(("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1}]))
        for label, params in tests:
            method = label.split("_")[0]
            lat, errs, size = [], {}, []
            for _ in range(a.n):
                dt, ok, err, nbytes, _r = c.call(method, params)
                if ok and dt is not None: lat.append(dt); size.append(nbytes)
                else: errs[err] = errs.get(err, 0) + 1
                time.sleep(a.pause)
            res["methods"][label] = {"ok": len(lat), "errors": errs, "p50_ms": pct(lat, .5), "p90_ms": pct(lat, .9),
                                     "p99_ms": pct(lat, .99), "min_ms": pct(lat, 0), "mean_ms": round(statistics.mean(lat), 3) if lat else None,
                                     "resp_bytes_p50": pct(size, .5)}
        out["providers"][name] = res
        print(f"== {name}", flush=True)
        cs = [x for x in res["cold"] if "error" not in x]
        if cs:
            print(f"  cold connect: dns {pct([x['dns_ms'] for x in cs], .5)} ms, tcp {pct([x['tcp_ms'] for x in cs], .5)} ms, "
                  f"tls {pct([x['tls_ms'] for x in cs], .5)} ms, first byte {pct([x['ttfb_ms'] for x in cs], .5)} ms, total {pct([x['total_ms'] for x in cs], .5)} ms (p50 of {len(cs)})")
        for label, m in res["methods"].items():
            print(f"  {label:26} ok {m['ok']:3}  p50 {m['p50_ms']}  p90 {m['p90_ms']}  p99 {m['p99_ms']}  min {m['min_ms']} ms  errors {m['errors'] or '-'}  ({m['resp_bytes_p50']} B)", flush=True)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(out, open(a.out, "w"), indent=1)
    print(f"wrote {a.out}")

if __name__ == "__main__":
    main()
