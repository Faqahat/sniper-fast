#!/usr/bin/env python3
"""Find each send endpoint's keep-alive IDLE TIMEOUT (zero cost: only ping/health requests).
For each idle gap X: open a connection, request once, sleep X, check whether the server closed the socket (FIN/RST seen
via a non-blocking peek), then request again on the same socket and time it. Runs hosts in parallel threads.
Prints one JSON line per (host, gap)."""
import os, sys, ssl, socket, time, json, threading, http.client, urllib.parse, select

def env(k): return os.environ.get(k, "")
EP = [
    ("helius-fra", "GET", "http://fra-sender.helius-rpc.com/ping", None),
    ("nozomi-fra2", "GET", "https://fra2.nozomi.temporal.xyz/ping", None),
    ("nozomi-fra2-http", "GET", "http://fra2.nozomi.temporal.xyz/ping", None),
    ("astralane-fr", "GET", "http://fr.gateway.astralane.io/gethealth", None),
    ("jito-fra", "GET", "https://frankfurt.mainnet.block-engine.jito.wtf/", None),
    ("ck-staked", "POST", "https://staked-rpc-frankfurt.constant-k.com/?api-key=" + env("CONSTANTK_TOKEN"), "rpc:getHealth"),
    ("speedlanding-fra", "GET", "http://fra.speedlanding.trade/ping", None),
    ("0slot-de", "GET", "http://de.0slot.trade/health", None),
    ("bloxroute-de", "GET", "http://germany.solana.dex.blxrbdn.com/", None),
    ("landx-fra1-http", "GET", "http://fra1.landx.dev/ping", None),
    ("lunar-fra", "GET", "http://fra.lunar-lander.hellomoon.io/ping", None),
    ("helius-global", "GET", "https://sender.helius-rpc.com/ping", None),
]
GAPS = [float(x) for x in (sys.argv[1].split(",") if len(sys.argv) > 1 else "1,2,4,6,10,16,31,46,61,91,121".split(","))]
lock = threading.Lock()

def closed(sock):
    try:
        sock.setblocking(False)
        try:
            d = sock.recv(1, socket.MSG_PEEK)
            return d == b""
        except (BlockingIOError, ssl.SSLWantReadError): return False
        except Exception: return True
        finally: sock.setblocking(True)
    except Exception: return True

def run(name, method, url, body):
    u = urllib.parse.urlsplit(url); host, port = u.hostname, u.port or (443 if u.scheme == "https" else 80)
    path = (u.path or "/") + ("?" + u.query if u.query else "")
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": body[4:], "params": []}).encode() if body else None
    hdr = {"content-type": "application/json"}
    def conn():
        if u.scheme == "https":
            ctx = ssl.create_default_context(); ctx.set_alpn_protocols(["http/1.1"])
            return http.client.HTTPSConnection(host, port, timeout=5, context=ctx)
        return http.client.HTTPConnection(host, port, timeout=5)
    for gap in GAPS:
        rec = {"name": name, "gap_s": gap}
        try:
            c = conn(); c.request(method, path, body=data, headers=hdr); r = c.getresponse(); r.read()
            rec["conn_hdr"] = r.getheader("connection"); rec["keepalive_hdr"] = r.getheader("keep-alive")
            time.sleep(gap)
            rec["server_closed"] = closed(c.sock)
            t = time.perf_counter()
            try:
                c.request(method, path, body=data, headers=hdr); r = c.getresponse(); r.read()
                rec["reuse_ms"] = round((time.perf_counter() - t) * 1e3, 2); rec["reused"] = True
            except Exception as e:
                rec["reused"] = False; rec["err"] = type(e).__name__
            c.close()
        except Exception as e:
            rec["setup_err"] = str(e)[:100]
        with lock: print(json.dumps(rec), flush=True)

ts = [threading.Thread(target=run, args=e) for e in EP]
for t in ts: t.start()
for t in ts: t.join()
