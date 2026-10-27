# sniper-rec remote storage backends (stdlib only). One interface:
#   connect() / close() / describe()
#   size(rel) -> int | None            remote file size (None = missing)
#   upload(local, rel)                 resumable, to "<rel>.part", SIZE-checked, then renamed to <rel>
#   sha256(rel) -> (hex, nbytes)       re-downloads and hashes (no remote hash command is assumed)
#   download(rel, local)               to "<local>.part", then renamed
#   listdir(rel_dir) -> [names]        delete(rel)
# rel paths are relative to the backend's base dir and use "/" separators.
# Backends: ftp (main: OVH Backup Storage; FTPS when the server offers it, plain FTP only if TLS fails, passive mode),
#           mount (any mounted path: NFS / CIFS / sshfs / a local dir for tests), rsync (rsync over ssh, or local).
import os, io, ssl, time, ftplib, hashlib, shutil, socket, subprocess, posixpath

CHUNK = 1 << 20
class BackendError(Exception): pass

def _sha_stream():
    h = hashlib.sha256(); n = [0]
    def cb(b): h.update(b); n[0] += len(b)
    return h, n, cb

# ------------------------------------------------------------------ FTP / FTPS
class FTPBackend:
    """OVH Backup Storage style FTP: passive mode, limited command set (no remote hash), usually only reachable from
    the server's own IP. TLS order: FTPS with certificate check -> FTPS without certificate check -> plain FTP; the mode
    actually used is in .mode and logged. Every operation reconnects and retries on dropped connections."""
    name = "ftp"
    def __init__(self, host, user, password, base="/sniper-rec", port=21, timeout=60, tls="auto", log=print, retries=4, mode_file=None):
        if not host: raise BackendError("FTP_HOST is empty (credentials not set yet)")
        self.host, self.user, self.pw, self.port, self.timeout = host, user, password, int(port or 21), timeout
        self.base = "/" + (base or "").strip("/") if base and base.strip("/") else ""
        self.tls = tls; self.log = log; self.retries = retries; self.ftp = None; self.mode = None; self.feats = set()
        self.mode_file = mode_file           # remembers the TLS mode per host: a host that did TLS is never downgraded to plain
    def describe(self): return f"ftp://{self.host}:{self.port}{self.base or '/'} ({self.mode or 'not connected'})"
    def _try(self, kind):
        if kind == "plain":
            f = ftplib.FTP(timeout=self.timeout); f.connect(self.host, self.port); f.login(self.user, self.pw); f.set_pasv(True); return f
        ctx = ssl.create_default_context()
        if kind == "ftps-unverified": ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        f = ftplib.FTP_TLS(context=ctx, timeout=self.timeout); f.connect(self.host, self.port); f.auth(); f.login(self.user, self.pw)
        f.prot_p(); f.set_pasv(True); return f
    def connect(self):
        self.close()
        order = {"auto": ["ftps-verified", "ftps-unverified", "plain"], "ftps": ["ftps-verified", "ftps-unverified"],
                 "plain": ["plain"]}[self.tls]
        known = {}
        if self.mode_file and os.path.exists(self.mode_file):
            try: known = __import__("json").load(open(self.mode_file))
            except Exception: known = {}
        prev = known.get(f"{self.host}:{self.port}")
        if prev and prev.startswith("ftps") and "plain" in order:
            order = [k for k in order if k != "plain"]          # TLS worked before: refuse a silent downgrade
        errs = []
        for kind in order:
            try:
                self.ftp = self._try(kind); self.mode = kind; break
            except ftplib.error_perm as e:
                if str(e).startswith("530"): raise BackendError(f"login refused ({kind}): {str(e)[:120]}")   # wrong user/password: do not fall through
                errs.append(f"{kind}: {str(e)[:120]}")
            except (ssl.SSLError, ftplib.Error, OSError, EOFError) as e:
                errs.append(f"{kind}: {type(e).__name__} {str(e)[:120]}")
        if self.ftp is None:
            raise BackendError("cannot connect: " + " | ".join(errs) + (f" (plain FTP not tried: this host did {prev} before)" if prev and prev.startswith("ftps") else ""))
        if errs: self.log(f"ftp: connected with {self.mode} after: " + " | ".join(errs))
        else: self.log(f"ftp: connected with {self.mode}")
        if self.mode_file and known.get(f"{self.host}:{self.port}") != self.mode and not (prev or "").startswith("ftps-verified"):
            known[f"{self.host}:{self.port}"] = self.mode
            try:
                tmp = self.mode_file + ".tmp"; __import__("json").dump(known, open(tmp, "w")); os.replace(tmp, self.mode_file)
            except OSError: pass
        try: self.feats = {l.strip().split()[0].upper() for l in self.ftp.sendcmd("FEAT").splitlines()[1:-1] if l.strip()}
        except ftplib.Error: self.feats = set()
        self.ftp.voidcmd("TYPE I")
        return self.mode
    def close(self):
        if self.ftp is not None:
            try: self.ftp.quit()
            except Exception:
                try: self.ftp.close()
                except Exception: pass
        self.ftp = None
    def _p(self, rel): return posixpath.join(self.base or "/", rel.lstrip("/"))
    def _retry(self, fn, what):
        last = None
        for i in range(self.retries + 2):
            try:
                if self.ftp is None: self.connect()
                return fn()
            except BackendError as e:                       # could not (re)connect: transient unless the login was refused
                if "login refused" in str(e) or "plain FTP not tried" in str(e): raise
                last = e; self.log(f"ftp: {what}: reconnect failed (retry {i + 1})"); time.sleep(min(30, 2 + 4 * i))
            except (ftplib.error_temp, EOFError, ConnectionError, socket.timeout, TimeoutError, ssl.SSLError, OSError) as e:
                last = e; self.log(f"ftp: {what}: {type(e).__name__} {str(e)[:100]} (retry {i + 1})"); self.close(); time.sleep(min(30, 2 + 4 * i))
        raise BackendError(f"{what}: {type(last).__name__} {last}")
    def size(self, rel):
        def f():
            try: return self.ftp.size(self._p(rel))
            except ftplib.error_perm: return None          # 550: no such file
        return self._retry(f, f"SIZE {rel}")
    def mkdirs(self, rel_dir):
        def f():
            cur = ""
            for part in [x for x in posixpath.join(self.base or "/", rel_dir).strip("/").split("/") if x]:
                cur = cur + "/" + part
                try: self.ftp.mkd(cur)
                except ftplib.error_perm: pass             # exists (or not allowed: the STOR will tell)
        return self._retry(f, f"MKD {rel_dir}")
    def upload(self, local, rel, progress=None):
        size = os.path.getsize(local); tmp = rel + ".part"
        self.mkdirs(posixpath.dirname(rel))
        for attempt in range(self.retries):
            have = self.size(tmp) or 0
            if have > size: self._retry(lambda: self.ftp.delete(self._p(tmp)), f"DELE {tmp}"); have = 0
            try:
                if self.ftp is None: self.connect()
                with open(local, "rb") as fh:
                    if have:
                        fh.seek(have)
                        try:
                            self.ftp.storbinary("STOR " + self._p(tmp), fh, blocksize=CHUNK, rest=have)       # REST + STOR
                        except ftplib.error_perm:
                            fh.seek(have); self.ftp.storbinary("APPE " + self._p(tmp), fh, blocksize=CHUNK)  # servers without REST STOR
                        self.log(f"ftp: resumed {rel} at {have}/{size}")
                    else:
                        self.ftp.storbinary("STOR " + self._p(tmp), fh, blocksize=CHUNK)
            except (ftplib.error_temp, EOFError, ConnectionError, socket.timeout, TimeoutError, ssl.SSLError, OSError) as e:
                self.log(f"ftp: upload {rel} interrupted: {type(e).__name__} {str(e)[:100]} (will resume)"); self.close(); time.sleep(min(30, 2 + 4 * attempt)); continue
            got = self.size(tmp)
            if got != size:
                self.log(f"ftp: {rel}: remote size {got} != local {size} after upload (retry)")
                if got is not None and got > size: self._retry(lambda: self.ftp.delete(self._p(tmp)), f"DELE {tmp}")
                continue
            def ren():
                if self._exists(rel): self.ftp.delete(self._p(rel))         # RNTO over an existing file fails on some servers
                self.ftp.rename(self._p(tmp), self._p(rel))
            self._retry(ren, f"RENAME {tmp}")
            if self.size(rel) != size: raise BackendError(f"{rel}: size after rename != {size}")
            return size
        raise BackendError(f"upload {rel} failed after {self.retries} attempts")
    def _exists(self, rel):
        try: self.ftp.size(self._p(rel)); return True
        except ftplib.error_perm: return False
    def sha256(self, rel):
        def f():
            h, n, cb = _sha_stream(); self.ftp.retrbinary("RETR " + self._p(rel), cb, blocksize=CHUNK); return h.hexdigest(), n[0]
        return self._retry(f, f"RETR {rel}")
    def download(self, rel, local):
        os.makedirs(os.path.dirname(local) or ".", exist_ok=True); tmp = local + ".part"
        def f():
            with open(tmp, "wb") as fh: self.ftp.retrbinary("RETR " + self._p(rel), fh.write, blocksize=CHUNK)
            os.replace(tmp, local); return os.path.getsize(local)
        return self._retry(f, f"RETR {rel}")
    def listdir(self, rel_dir):
        def f():
            try: return sorted(posixpath.basename(x) for x in self.ftp.nlst(self._p(rel_dir)))
            except ftplib.error_perm as e:
                if str(e).startswith("550"): return []
                raise
        return self._retry(f, f"NLST {rel_dir}")
    def delete(self, rel): return self._retry(lambda: self.ftp.delete(self._p(rel)), f"DELE {rel}")

# ------------------------------------------------------------------ mounted path (NFS/CIFS/sshfs) or a local dir (tests)
class MountBackend:
    name = "mount"
    def __init__(self, base, log=print, **_):
        if not base: raise BackendError("REC_REMOTE_PATH is empty")
        self.base = base; self.log = log; self.mode = "mount"
    def describe(self): return f"mount:{self.base}"
    def connect(self):
        if not os.path.isdir(self.base): raise BackendError(f"{self.base} is not a mounted directory")
        return "mount"
    def close(self): pass
    def _p(self, rel): return os.path.join(self.base, rel.lstrip("/"))
    def size(self, rel):
        try: return os.path.getsize(self._p(rel))
        except FileNotFoundError: return None
    def upload(self, local, rel, progress=None):
        size = os.path.getsize(local); dst = self._p(rel); tmp = dst + ".part"; os.makedirs(os.path.dirname(dst), exist_ok=True)
        have = os.path.getsize(tmp) if os.path.exists(tmp) else 0
        if have > size: os.remove(tmp); have = 0
        with open(local, "rb") as src, open(tmp, "ab" if have else "wb") as out:
            src.seek(have); shutil.copyfileobj(src, out, CHUNK); out.flush(); os.fsync(out.fileno())
        if have: self.log(f"mount: resumed {rel} at {have}/{size}")
        if os.path.getsize(tmp) != size: raise BackendError(f"{rel}: size {os.path.getsize(tmp)} != {size}")
        os.replace(tmp, dst); return size
    def sha256(self, rel):
        h, n, cb = _sha_stream()
        with open(self._p(rel), "rb") as f:
            for b in iter(lambda: f.read(CHUNK), b""): cb(b)
        return h.hexdigest(), n[0]
    def download(self, rel, local):
        os.makedirs(os.path.dirname(local) or ".", exist_ok=True); shutil.copyfile(self._p(rel), local + ".part"); os.replace(local + ".part", local)
        return os.path.getsize(local)
    def listdir(self, rel_dir):
        try: return sorted(os.listdir(self._p(rel_dir)))
        except FileNotFoundError: return []
    def delete(self, rel): os.remove(self._p(rel))

# ------------------------------------------------------------------ rsync (over ssh: REC_REMOTE_SSH=user@host [port]; or local)
class RsyncBackend:
    """rsync --partial into <rel>.part then an atomic rename (ssh mv); sha256 by re-download through `ssh cat` (works
    on rsync-only accounts too, as long as cat is allowed) or locally. sftp-only accounts: mount them with sshfs and use
    the mount backend."""
    name = "rsync"
    def __init__(self, base, ssh="", port="22", log=print, **_):
        self.base = base; self.ssh = ssh; self.port = str(port or 22); self.log = log; self.mode = "rsync+ssh" if ssh else "rsync-local"
    def describe(self): return f"rsync:{self.ssh + ':' if self.ssh else ''}{self.base}"
    def _sshc(self): return ["ssh", "-p", self.port, "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", self.ssh]
    def _p(self, rel): return posixpath.join(self.base, rel.lstrip("/"))
    def _run(self, remote_cmd):
        if self.ssh: return subprocess.run(self._sshc() + [remote_cmd], capture_output=True, text=True, timeout=600)
        return subprocess.run(["bash", "-c", remote_cmd], capture_output=True, text=True, timeout=600)
    def connect(self):
        r = self._run(f"mkdir -p '{self.base}' && echo ok")
        if r.returncode != 0 or "ok" not in r.stdout: raise BackendError("rsync remote not reachable: " + r.stderr[-200:])
        return self.mode
    def close(self): pass
    def size(self, rel):
        r = self._run(f"stat -c %s '{self._p(rel)}' 2>/dev/null")
        return int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip().isdigit() else None
    def upload(self, local, rel, progress=None):
        size = os.path.getsize(local); dst = self._p(rel)
        self._run(f"mkdir -p '{posixpath.dirname(dst)}'")
        tgt = (f"{self.ssh}:" if self.ssh else "") + dst + ".part"
        cmd = ["rsync", "--partial", "--inplace", "-t"] + (["-e", f"ssh -p {self.port} -o BatchMode=yes"] if self.ssh else []) + [local, tgt]
        for i in range(4):
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode == 0: break
            self.log(f"rsync: {rel}: rc {r.returncode} {r.stderr[-160:]} (retry)"); time.sleep(5 + 5 * i)
        else: raise BackendError(f"rsync {rel} failed")
        if self.size(rel + ".part") != size: raise BackendError(f"{rel}: remote size mismatch")
        r = self._run(f"mv -f '{dst}.part' '{dst}'")
        if r.returncode != 0: raise BackendError(f"rename {rel}: {r.stderr[-160:]}")
        return size
    def sha256(self, rel):
        h, n, cb = _sha_stream()
        cmd = (self._sshc() + [f"cat '{self._p(rel)}'"]) if self.ssh else ["cat", self._p(rel)]
        with subprocess.Popen(cmd, stdout=subprocess.PIPE) as pr:
            for b in iter(lambda: pr.stdout.read(CHUNK), b""): cb(b)
        if pr.returncode != 0: raise BackendError(f"read {rel} failed")
        return h.hexdigest(), n[0]
    def download(self, rel, local):
        os.makedirs(os.path.dirname(local) or ".", exist_ok=True)
        src = (f"{self.ssh}:" if self.ssh else "") + self._p(rel)
        r = subprocess.run(["rsync", "-t"] + (["-e", f"ssh -p {self.port} -o BatchMode=yes"] if self.ssh else []) + [src, local + ".part"], capture_output=True, text=True)
        if r.returncode != 0: raise BackendError(f"download {rel}: {r.stderr[-160:]}")
        os.replace(local + ".part", local); return os.path.getsize(local)
    def listdir(self, rel_dir):
        r = self._run(f"ls -1 '{self._p(rel_dir)}' 2>/dev/null"); return sorted(x for x in r.stdout.splitlines() if x)
    def delete(self, rel): self._run(f"rm -f '{self._p(rel)}'")

def from_env(log=print):
    kind = os.environ.get("REC_REMOTE", "ftp")
    if kind == "ftp":
        return FTPBackend(os.environ.get("FTP_HOST", ""), os.environ.get("FTP_USER", ""), os.environ.get("FTP_PASS", ""),
                          os.environ.get("FTP_DIR", "/sniper-rec"), os.environ.get("FTP_PORT", "21"),
                          tls=os.environ.get("FTP_TLS", "auto"), log=log,
                          mode_file=os.path.join(os.environ.get("REC_ROOT", "/home/moiz/sniper-data/rec"), "state", "ftp_mode.json"))
    if kind == "mount": return MountBackend(os.environ.get("REC_REMOTE_PATH", ""), log=log)
    if kind == "rsync": return RsyncBackend(os.environ.get("REC_REMOTE_PATH", ""), os.environ.get("REC_REMOTE_SSH", ""), os.environ.get("REC_REMOTE_SSH_PORT", "22"), log=log)
    raise BackendError(f"unknown REC_REMOTE={kind} (ftp | mount | rsync; s3 not built yet)")
