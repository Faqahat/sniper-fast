#!/usr/bin/env python3
# END-TO-END test of the archive tier against LOCAL servers only (never anything external):
#  A) FTP backend vs a local pyftpdlib server: FTPS with a self-signed cert (verified -> unverified fallback, mode logged),
#     plain server (AUTH TLS refused -> plain), wrong password (refused, no fall-through), no downgrade to plain for a host
#     that did TLS before, upload to .part + rename, SIZE, re-download sha256, resume from a partial .part (REST), resume
#     after the server is killed mid-upload.
#  B) rec archive / fetch / due / pin / cache eviction through rec.py with REC_REMOTE=ftp, then mount, then rsync (local).
# Usage: test_archive.py <dir with pyftpdlib+OpenSSL on sys.path> <cert.pem> <key.pem> <a finished day dir to copy>
import os, sys, json, time, shutil, socket, subprocess, hashlib, threading, glob
HERE = os.path.dirname(os.path.abspath(__file__)); REC = os.path.dirname(HERE); sys.path.insert(0, REC)
PYLIB, CERT, KEY, SRCDAY = sys.argv[1:5]
WORK = os.environ.get("TEST_WORK", "/home/moiz/sniper-data/rec/test/archive")
shutil.rmtree(WORK, ignore_errors=True); os.makedirs(WORK)
import backends as B
FAILS = []; LOG = []
def check(c, what):
    print(("PASS " if c else "FAIL ") + what, flush=True)
    if not c: FAILS.append(what)
def lg(m): LOG.append(m)
def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p
SERVER = r'''
import sys; sys.path.insert(0, sys.argv[1])
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler, TLS_FTPHandler, ThrottledDTPHandler
from pyftpdlib.servers import FTPServer
import logging; logging.disable(logging.CRITICAL)
port, root, tls, thr = int(sys.argv[2]), sys.argv[3], sys.argv[4] == "1", int(sys.argv[5])
a = DummyAuthorizer(); a.add_user("rec", "pw", root, perm="elradfmwMT")
H = TLS_FTPHandler if tls else FTPHandler
if tls: H.certfile = sys.argv[6]; H.keyfile = sys.argv[7]
if thr:
    class T(ThrottledDTPHandler): read_limit = thr; write_limit = thr
    H.dtp_handler = T
H.authorizer = a; H.passive_ports = range(port + 1, port + 40)
FTPServer(("127.0.0.1", port), H).serve_forever()
'''
open(os.path.join(WORK, "ftpd.py"), "w").write(SERVER)
def serve(root, tls, port=None, thr=0):
    port = port or free_port(); os.makedirs(root, exist_ok=True)
    p = subprocess.Popen([sys.executable, os.path.join(WORK, "ftpd.py"), PYLIB, str(port), root, "1" if tls else "0", str(thr), CERT, KEY],
                         stdout=subprocess.DEVNULL, stderr=open(os.path.join(WORK, "ftpd.err"), "a"))
    for _ in range(100):
        try: socket.create_connection(("127.0.0.1", port), 0.2).close(); break
        except OSError: time.sleep(0.05)
    return p, port
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()

# ---------------- A) FTP backend ----------------
root = os.path.join(WORK, "ftps_root"); srv, port = serve(root, True)
src = os.path.join(WORK, "src.bin"); open(src, "wb").write(os.urandom(24 << 20))
modef = os.path.join(WORK, "ftp_mode.json")
be = B.FTPBackend("127.0.0.1", "rec", "pw", "/archive", port, tls="auto", log=lg, mode_file=modef)
mode = be.connect()
check(mode == "ftps-unverified", f"FTPS server with a self-signed cert: verified TLS refused, unverified TLS used (mode {mode}); log: {LOG[-1][:120]}")
be.upload(src, "days/2026-01-01/txs/a.bin")
check(be.size("days/2026-01-01/txs/a.bin") == os.path.getsize(src) and be.size("days/2026-01-01/txs/a.bin.part") is None, "upload went to .part, then renamed; remote SIZE == local")
h, n = be.sha256("days/2026-01-01/txs/a.bin")
check(h == sha(src) and n == os.path.getsize(src), "re-download sha256 matches")
part = os.path.join(root, "archive", "days", "2026-01-01", "txs", "b.bin.part")
open(part, "wb").write(open(src, "rb").read(7 << 20))                      # a partial upload left behind
LOG.clear(); be.upload(src, "days/2026-01-01/txs/b.bin")
check(any("resumed" in l for l in LOG) and sha(os.path.join(root, "archive", "days", "2026-01-01", "txs", "b.bin")) == sha(src), f"resume from a partial .part via REST: {[l for l in LOG if 'resumed' in l]}")
be.close(); srv.kill(); srv.wait()
# interrupted mid-upload: throttled plain server killed after 2 s, restarted 2 s later on the same port
root2 = os.path.join(WORK, "plain_root"); srv, port2 = serve(root2, False, thr=4 << 20)
big = os.path.join(WORK, "big.bin"); open(big, "wb").write(os.urandom(40 << 20))
be2 = B.FTPBackend("127.0.0.1", "rec", "pw", "/", port2, tls="auto", log=lg); LOG.clear()
m2 = be2.connect()
check(m2 == "plain", f"server without TLS: AUTH TLS refused -> plain FTP, logged ({[l for l in LOG if 'connected' in l][-1][:150]})")
def killer():
    time.sleep(2.0); srv.kill(); srv.wait(); time.sleep(2.0); globals()["srv"], _ = serve(root2, False, port=port2)
t = threading.Thread(target=killer); t.start(); LOG.clear(); t0 = time.time()
be2.upload(big, "x/big.bin"); t.join()
check(sha(os.path.join(root2, "x", "big.bin")) == sha(big) and any("interrupted" in l for l in LOG) and any("resumed" in l for l in LOG),
      f"server killed mid-upload -> reconnect + resume -> complete file ({time.time() - t0:.1f} s; {[l[:80] for l in LOG if 'interrupted' in l or 'resumed' in l][:3]})")
be2.close()
bad = B.FTPBackend("127.0.0.1", "rec", "WRONG", "/", port2, tls="plain", log=lg)
try: bad.connect(); check(False, "wrong password refused")
except B.BackendError as e: check("login refused" in str(e), f"wrong password -> 'login refused', no fall-through ({str(e)[:80]})")
# no downgrade: this host:port did FTPS before (recorded in the mode file) -> plain is not tried
json.dump({f"127.0.0.1:{port2}": "ftps-unverified"}, open(modef, "w"))
nd = B.FTPBackend("127.0.0.1", "rec", "pw", "/", port2, tls="auto", log=lg, mode_file=modef)
try: nd.connect(); check(False, "no downgrade to plain for a host that did TLS before")
except B.BackendError as e: check("plain FTP not tried" in str(e), "no downgrade to plain for a host that did TLS before (refused)")
srv.kill(); srv.wait()

# ---------------- B) rec archive / fetch / due / pin / cache through rec.py ----------------
def run_rec(env, *args):
    e = dict(os.environ); [e.pop(k) for k in list(e) if k.startswith(("REC_", "FTP_", "TELEGRAM", "SHYFT", "RMR", "CONSTANTK"))]
    e.update(env); r = subprocess.run([sys.executable, "-I", os.path.join(REC, "rec.py")] + list(args), env=e, capture_output=True, text=True, timeout=600)
    return r.returncode, r.stdout + r.stderr
day = os.path.basename(SRCDAY.rstrip("/"))
for kind in ("ftp", "mount", "rsync"):
    tr = os.path.join(WORK, f"root_{kind}"); os.makedirs(os.path.join(tr, "days")); shutil.copytree(SRCDAY, os.path.join(tr, "days", day))
    want = {os.path.relpath(p, SRCDAY): sha(p) for p in glob.glob(os.path.join(SRCDAY, "**"), recursive=True) if os.path.isfile(p)}
    env = dict(REC_ROOT=tr, REC_LEGACY=os.path.join(tr, "nolegacy"), REC_HOST_KEEP_DAYS="0", REC_REMOTE=kind, REC_CACHE_CAP_GB="60")
    if kind == "ftp":
        rroot = os.path.join(WORK, "rec_ftp_root"); srv, p3 = serve(rroot, True)
        env.update(FTP_HOST="127.0.0.1", FTP_PORT=str(p3), FTP_USER="rec", FTP_PASS="pw", FTP_DIR="/sniper-rec"); remote_base = os.path.join(rroot, "sniper-rec")
    else:
        remote_base = os.path.join(WORK, f"remote_{kind}"); os.makedirs(remote_base); env.update(REC_REMOTE_PATH=remote_base)
    rc, out = run_rec(env, "catalog"); rc, out = run_rec(env, "archive")
    cat = json.load(open(os.path.join(tr, "catalog.json"))); e = cat["days"][day]
    got = {os.path.relpath(p, os.path.join(remote_base, "days", day)): sha(p) for p in glob.glob(os.path.join(remote_base, "days", day, "**"), recursive=True) if os.path.isfile(p)}
    check(rc == 0 and got == want, f"[{kind}] archive uploaded every file with identical sha256 ({len(got)}/{len(want)} files) rc {rc}")
    check(not os.path.exists(os.path.join(tr, "days", day)) and e.get("where") == ["remote"] and e["remote"]["verify"] == "sha256-full",
          f"[{kind}] host copy removed only after verification; catalog where={e.get('where')} verify={e.get('remote', {}).get('verify')}")
    check(os.path.exists(os.path.join(remote_base, "manifests", day + ".sha256")), f"[{kind}] manifest uploaded")
    rc, out = run_rec(env, "fetch", day)
    cp = os.path.join(tr, "cache", "days", day)
    check(rc == 0 and {os.path.relpath(p, cp): sha(p) for p in glob.glob(os.path.join(cp, "**"), recursive=True) if os.path.isfile(p)} == want, f"[{kind}] fetch -> cache, sha256 verified")
    rc, out = run_rec(env, "path", day); check(out.strip() == cp, f"[{kind}] rec path -> cache path")
    rc, out = run_rec(dict(env, REC_REMOTE_KEEP_DAYS="0"), "due"); check(day in out, f"[{kind}] rec due lists it (never deletes)")
    if kind == "ftp":
        # corrupt the remote copy of one file -> a fresh fetch must refuse it
        shutil.rmtree(cp); victim = sorted(glob.glob(os.path.join(remote_base, "days", day, "txs", "*.gz")))[0]
        b = bytearray(open(victim, "rb").read()); b[len(b) // 2] ^= 0xFF; open(victim, "wb").write(bytes(b))
        rc, out = run_rec(env, "fetch", day); check(rc != 0 and "sha256 mismatch" in out, "corrupted remote file is refused on fetch (sha256 mismatch)")
        # pins + LRU: a tiny cap evicts unpinned days, never pinned ones
        open(victim, "wb").write(bytes(b[:len(b) // 2]) + bytes([b[len(b) // 2] ^ 0xFF]) + bytes(b[len(b) // 2 + 1:]))
        rc, out = run_rec(env, "fetch", day); run_rec(env, "pin", day)
        rc, out = run_rec(dict(env, REC_CACHE_CAP_GB="0.000001"), "fetch", day)
        check(os.path.isdir(cp), "pinned day is never evicted from the cache, even over the cap")
        run_rec(env, "unpin", day); fake = os.path.join(tr, "cache", "days", "2026-01-02"); os.makedirs(os.path.join(fake, "txs")); open(os.path.join(fake, "txs", "x"), "wb").write(b"x" * 1000)
        cat = json.load(open(os.path.join(tr, "catalog.json"))); cat["days"]["2026-01-02"] = dict(kind="rec", where=["cache", "remote"], remote=dict(verified=1)); json.dump(cat, open(os.path.join(tr, "catalog.json"), "w"))
        rc, out = run_rec(dict(env, REC_CACHE_CAP_GB="0.000001"), "fetch", day)
        check(not os.path.exists(fake) and os.path.isdir(cp), f"over the cap: the least-recently-used unpinned day is evicted, the day just fetched is kept")
        srv.kill(); srv.wait()
print("\nRESULT:", "ALL PASSED" if not FAILS else f"{len(FAILS)} FAILED: {FAILS}")
sys.exit(1 if FAILS else 0)
