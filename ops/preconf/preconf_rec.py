#!/usr/bin/env python3
"""PRECONF RECORDER (owner 10-27 ~21:40 PKT: 1-hour Helius pre-confirmation trial). Read-only measurement, no trading.
Subscribes to Helius `preconfSubscribe` (wss://beta.helius-rpc.com, pump.fun program only) and writes every binary
notification with its local receive time (CLOCK_REALTIME ns, the same clock as the engine's `t` fields), so the frames can be
matched by signature against the live engine's records afterwards.
Output (DIR, default /root/preconf): frames.bin = repeated [u64 recv_ns LE][u32 len LE][frame bytes]; rec.log = status lines.
Frame layout (Helius docs): u8 version | u64 slot | u64 tx_index | u8 status (0 failed, 1 ok, 2 unknown/BAM) | tx wire bytes.
The API key is read from KEYFILE (default /root/preconf.key) and never printed. Stops after --minutes and unsubscribes.
Standard library only (the nodes have no websocket package)."""
import argparse, base64, json, os, socket, ssl, struct, sys, time

HOST = "beta.helius-rpc.com"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"


def log(fh, msg):
    line = f"{time.strftime('%H:%M:%S', time.gmtime(time.time() + 5 * 3600))} PKT {msg}"
    fh.write(line + "\n"); fh.flush(); print(line, flush=True)


class WS:
    def __init__(self, key, timeout=20):
        raw = socket.create_connection((HOST, 443), timeout=timeout)
        raw.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.s = ssl.create_default_context().wrap_socket(raw, server_hostname=HOST)
        k = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET /?api-key={key} HTTP/1.1\r\nHost: {HOST}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {k}\r\nSec-WebSocket-Version: 13\r\nUser-Agent: rewind-preconf-rec/1\r\n\r\n")
        self.s.sendall(req.encode())
        hdr = b""
        while b"\r\n\r\n" not in hdr:
            c = self.s.recv(4096)
            if not c: raise ConnectionError("closed during handshake")
            hdr += c
        head, self.buf = hdr.split(b"\r\n\r\n", 1)
        status = head.split(b"\r\n", 1)[0].decode(errors="replace")
        if " 101 " not in status + " ":
            raise ConnectionError(f"handshake refused: {status}")   # the status line never contains the key
        self.s.settimeout(1.0)

    def _send(self, op, payload=b""):
        mask = os.urandom(4); n = len(payload)
        h = bytes([0x80 | op])
        if n < 126: h += bytes([0x80 | n])
        elif n < 65536: h += bytes([0x80 | 126]) + struct.pack(">H", n)
        else: h += bytes([0x80 | 127]) + struct.pack(">Q", n)
        self.s.sendall(h + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def send_text(self, t): self._send(0x1, t.encode())
    def ping(self): self._send(0x9, b"r")
    def close(self):
        try: self._send(0x8, struct.pack(">H", 1000))
        except Exception: pass
        try: self.s.close()
        except Exception: pass

    def _need(self, n):
        while len(self.buf) < n:
            c = self.s.recv(65536)
            if not c: raise ConnectionError("connection closed")
            self.buf += c

    def recv(self):
        """one complete message: (opcode, payload); None on a read timeout with no partial frame pending"""
        parts = []; op0 = None
        while True:
            try:
                self._need(2)
            except socket.timeout:
                if not parts and len(self.buf) == 0: return None
                continue
            b0, b1 = self.buf[0], self.buf[1]; fin = b0 & 0x80; op = b0 & 0x0F; n = b1 & 0x7F; off = 2
            if n == 126: self._need(4); n = struct.unpack(">H", self.buf[2:4])[0]; off = 4
            elif n == 127: self._need(10); n = struct.unpack(">Q", self.buf[2:10])[0]; off = 10
            if b1 & 0x80: self._need(off + 4); mk = self.buf[off:off + 4]; off += 4
            else: mk = None
            while True:
                try: self._need(off + n); break
                except socket.timeout: continue
            p = self.buf[off:off + n]; self.buf = self.buf[off + n:]
            if mk: p = bytes(b ^ mk[i % 4] for i, b in enumerate(p))
            if op == 0x9: self._send(0xA, p); continue          # ping -> pong
            if op == 0xA: continue                              # pong
            if op == 0x8: raise ConnectionError(f"server closed: {p[:2].hex()} {p[2:120].decode(errors='replace')}")
            if op != 0: op0 = op
            parts.append(p)
            if fin: return op0, b"".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=58.0)
    ap.add_argument("--dir", default="/root/preconf")
    ap.add_argument("--keyfile", default="/root/preconf.key")
    ap.add_argument("--all", action="store_true", help="no pump.fun filter (much more volume and credits)")
    A = ap.parse_args()
    key = open(A.keyfile).read().strip()
    if not key or any(c.isspace() for c in key): sys.exit("bad key file")
    os.makedirs(A.dir, exist_ok=True)
    lf = open(f"{A.dir}/rec.log", "a"); out = open(f"{A.dir}/frames.bin", "ab")
    params = [] if A.all else [{"accountInclude": [PUMP]}]
    sub = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "preconfSubscribe", "params": params})
    end = time.time() + A.minutes * 60
    n = nb = 0; st = {0: 0, 1: 0, 2: 0}; last_slot = 0; last_stat = time.time(); last_ping = time.time()
    log(lf, f"start: {A.minutes:.0f} min, filter {'none' if A.all else 'pump.fun program'}, out {A.dir}/frames.bin")
    backoff = 1
    while time.time() < end:
        ws = None; sid = None
        try:
            ws = WS(key); log(lf, "connected"); ws.send_text(sub); backoff = 1
            while time.time() < end:
                m = ws.recv(); now = time.time_ns()
                if m is not None:
                    op, p = m
                    if op == 0x2:
                        out.write(struct.pack("<QI", now, len(p))); out.write(p); n += 1; nb += len(p)
                        if len(p) >= 18:
                            last_slot = struct.unpack_from("<Q", p, 1)[0]; s = p[17]; st[s] = st.get(s, 0) + 1
                    elif op == 0x1:
                        txt = p.decode(errors="replace")
                        try:
                            j = json.loads(txt)
                            if j.get("id") == 1 and "result" in j: sid = j["result"]; log(lf, f"subscribed, id {sid}")
                            else: log(lf, "text: " + txt[:300])
                        except Exception: log(lf, "text: " + txt[:300])
                t = time.time()
                if t - last_ping > 20: ws.ping(); last_ping = t
                if t - last_stat > 30:
                    out.flush()
                    log(lf, f"frames {n} ({nb / 1e6:.1f} MB) status ok {st.get(1, 0)} failed {st.get(0, 0)} unknown/BAM {st.get(2, 0)} | last slot {last_slot}")
                    last_stat = t
            if sid is not None:
                ws.send_text(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "preconfUnsubscribe", "params": [sid]}))
                log(lf, "unsubscribed (time up)"); time.sleep(1)
            ws.close()
        except Exception as e:
            log(lf, f"error: {type(e).__name__}: {str(e)[:200]}; reconnect in {backoff} s")
            if ws: ws.close()
            time.sleep(backoff); backoff = min(backoff * 2, 30)
    out.flush()
    log(lf, f"done: frames {n} ({nb / 1e6:.1f} MB) status ok {st.get(1, 0)} failed {st.get(0, 0)} unknown/BAM {st.get(2, 0)}")


if __name__ == "__main__":
    main()
