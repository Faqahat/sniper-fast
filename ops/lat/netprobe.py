#!/usr/bin/env python3
"""Zero-cost network probe of every send endpoint from this server (no transaction is sent).
Per endpoint: DNS time + IPs, ICMP RTT, TCP connect, TLS handshake (+ALPN), cold request (curl-like), warm keep-alive
request RTT over one persistent connection. Prints hosts only (never URLs with keys).
usage: netprobe.py [--warm N] [--only substr] > out.json"""
import os, sys, ssl, socket, time, json, subprocess, statistics, http.client, urllib.parse

def env(k): return os.environ.get(k, "")

# (name, method, url, body) -- url may hold a key: never printed; ping/health endpoints documented by each provider
EP = [
    ("helius-fra",      "GET",  "http://fra-sender.helius-rpc.com/ping", None),
    ("helius-fra-tls",  "GET",  "https://fra-sender.helius-rpc.com/ping", None),
    ("helius-global",   "GET",  "https://sender.helius-rpc.com/ping", None),
    ("jito-fra",        "POST", "https://frankfurt.mainnet.block-engine.jito.wtf/api/v1/getTipAccounts", "rpc:getTipAccounts"),
    ("jito-ams",        "POST", "https://amsterdam.mainnet.block-engine.jito.wtf/api/v1/getTipAccounts", "rpc:getTipAccounts"),
    ("jito-lon",        "POST", "https://london.mainnet.block-engine.jito.wtf/api/v1/getTipAccounts", "rpc:getTipAccounts"),
    ("jito-dub",        "POST", "https://dublin.mainnet.block-engine.jito.wtf/api/v1/getTipAccounts", "rpc:getTipAccounts"),
    ("nozomi-fra2",     "GET",  "https://fra2.nozomi.temporal.xyz/ping", None),
    ("nozomi-fra2-http","GET",  "http://fra2.nozomi.temporal.xyz/ping", None),
    ("nozomi-ams1",     "GET",  "https://ams1.nozomi.temporal.xyz/ping", None),
    ("nozomi-fra1",     "GET",  "https://fra1.nozomi.temporal.xyz/ping", None),
    ("landx-fra1-http", "GET",  "http://fra1.landx.dev/ping", None),
    ("landx-fra3",      "ICMP", "udp://fra3.landx.dev:10000", None),
    ("astralane-fr",    "GET",  "http://fr.gateway.astralane.io/gethealth", None),
    ("astralane-fr-tls","GET",  "https://fr.gateway.astralane.io/gethealth", None),
    ("0slot-de",        "GET",  "http://de.0slot.trade/health", None),
    ("bloxroute-de",    "GET",  "http://germany.solana.dex.blxrbdn.com/", None),
    ("nextblock-fra",   "GET",  "https://frankfurt.nextblock.io/", None),
    ("blockrazor-fra",  "GET",  "http://frankfurt.solana.blockrazor.xyz:443/health", None),
    ("speedlanding-fra","GET",  "http://fra.speedlanding.trade/ping", None),
    ("lunar-fra",       "GET",  "http://fra.lunar-lander.hellomoon.io/ping", None),
    ("bolt-fra",        "GET",  "https://fra.bolt.raiden.wtf/ping", None),
    ("falcon-fra",      "POST", "http://fra.falcon.wtf/", "rpc:getHealth"),
    ("node1-fra",       "GET",  "http://fra.node1.me/ping", None),
    ("everstake-fra",   "POST", "http://fra-swqos.everstake.one/", "rpc:getHealth"),
    ("flashblock-fra",  "GET",  "http://fra.flashblock.trade/", None),
    ("ck-staked",       "POST", "https://staked-rpc-frankfurt.constant-k.com/?api-key=" + env("CONSTANTK_TOKEN"), "rpc:getHealth"),
    ("ck-rpc",          "POST", "https://rpc-frankfurt.constant-k.com/?api-key=" + env("CONSTANTK_TOKEN"), "rpc:getHealth"),
    ("ck-kaldera",      "TLS",  "https://kaldera-frankfurt.constant-k.com:8443", None),
    ("ck-turbo-kaldera","TLS",  "https://turbo-kaldera-frankfurt.constant-k.com:443", None),
    ("erpc-shreds-fra6","TLS",  "https://shreds-fra6-1.erpc.global", None),
    ("astralane-shreds","ICMP", "http://fr2.shreds.astralane.io:12000", None),
]

def body_of(b):
    if b and b.startswith("rpc:"):
        return json.dumps({"jsonrpc": "2.0", "id": 1, "method": b[4:], "params": []}).encode()
    return None

def ping(host, n=10):
    try:
        out = subprocess.run(["ping", "-n", "-c", str(n), "-i", "0.2", "-W", "1", host], capture_output=True, text=True, timeout=10).stdout
        for ln in out.splitlines():
            if "min/avg" in ln: a = ln.split("=")[1].strip().split()[0].split("/"); return {"min": float(a[0]), "avg": float(a[1])}
        return None
    except Exception: return None

def pct(v, q):
    v = sorted(v); return round(v[min(len(v) - 1, int(round((len(v) - 1) * q)))], 3) if v else None

def probe(name, method, url, body, warm_n):
    u = urllib.parse.urlsplit(url)
    host, port = u.hostname, u.port or (443 if u.scheme == "https" else 80)
    r = {"name": name, "host": host, "port": port, "scheme": u.scheme}
    t = time.perf_counter()
    try:
        ai = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
    except Exception as e:
        r["error"] = f"dns: {e}"; return r
    r["dns_ms"] = round((time.perf_counter() - t) * 1e3, 2)
    ips = sorted({a[4][0] for a in ai}); r["ips"] = ips
    r["icmp"] = ping(ips[0])
    if method == "ICMP": return r
    # TCP connect x5
    tc = []
    for _ in range(5):
        s = socket.socket(); s.settimeout(3)
        t = time.perf_counter()
        try: s.connect((ips[0], port)); tc.append((time.perf_counter() - t) * 1e3)
        except Exception as e: r["tcp_error"] = str(e)
        finally: s.close()
        time.sleep(0.05)
    r["tcp_ms"] = {"min": pct(tc, 0), "p50": pct(tc, .5)} if tc else None
    if u.scheme == "https":
        ctx = ssl.create_default_context(); ctx.set_alpn_protocols(["h2", "http/1.1"])
        th = []
        for _ in range(3):
            try: s = socket.create_connection((ips[0], port), timeout=3)
            except Exception as e: r["tls_error"] = "connect: " + str(e)[:80]; break
            t = time.perf_counter()
            try:
                ss = ctx.wrap_socket(s, server_hostname=host); th.append((time.perf_counter() - t) * 1e3)
                r["alpn"] = ss.selected_alpn_protocol(); r["tls"] = ss.version(); ss.close()
            except Exception as e: r["tls_error"] = str(e)[:120]; s.close()
            time.sleep(0.05)
        r["tls_hs_ms"] = {"min": pct(th, 0), "p50": pct(th, .5)} if th else None
    if method == "TLS": return r
    path = u.path or "/"
    if u.query: path += "?" + u.query
    hdr = {"content-type": "application/json", "connection": "keep-alive"}
    data = body_of(body)
    def conn():
        if u.scheme == "https":
            ctx = ssl.create_default_context(); ctx.set_alpn_protocols(["http/1.1"])
            return http.client.HTTPSConnection(host, port, timeout=5, context=ctx)
        return http.client.HTTPConnection(host, port, timeout=5)
    # cold request (new connection incl. handshake)
    try:
        c = conn(); t = time.perf_counter(); c.request(method, path, body=data, headers=hdr); resp = c.getresponse(); b = resp.read()
        r["cold_ms"] = round((time.perf_counter() - t) * 1e3, 2); r["status"] = resp.status
        r["reply"] = b[:80].decode("utf-8", "replace").replace(env("CONSTANTK_TOKEN") or "\0", "<k>")
        r["server_hdr"] = {k: v for k, v in resp.getheaders() if k.lower() in ("server", "connection", "keep-alive", "via", "cf-ray", "alt-svc")}
        warm = []; reconnects = 0
        for i in range(warm_n):
            time.sleep(0.25 if body != "rpc:getTipAccounts" else 1.1)
            t = time.perf_counter()
            try:
                c.request(method, path, body=data, headers=hdr); resp = c.getresponse(); resp.read()
                warm.append((time.perf_counter() - t) * 1e3)
                if resp.status == 429: r["got_429"] = True
            except Exception:
                reconnects += 1; c.close(); c = conn()
        c.close()
        r["warm_ms"] = {"n": len(warm), "min": pct(warm, 0), "p50": pct(warm, .5), "p90": pct(warm, .9)}
        r["warm_reconnects"] = reconnects
    except Exception as e:
        r["http_error"] = str(e)[:160]
    return r

if __name__ == "__main__":
    warm_n = int(sys.argv[sys.argv.index("--warm") + 1]) if "--warm" in sys.argv else 15
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else ""
    out = []
    for e in EP:
        if only and only not in e[0]: continue
        try: r = probe(*e, warm_n)
        except Exception as ex: r = {"name": e[0], "error": str(ex)[:160]}
        out.append(r)
        print(json.dumps(r), flush=True)
