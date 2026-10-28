#!/usr/bin/env python3
"""Archive old study DATA to the OVH backup, then free it locally (owner 10-29: old study data not needed locally).
usage: archive_dir.py <dir> <remote_name>   (env: /etc/sniper-rec/env FTP_*)
Per <dir>: tar every file (data + code) into <scratch>/<remote_name>.tar, sha256 it, upload to FTP_DIR/archive/<remote_name>.tar,
re-download through sha256 and compare. Only on a match: delete the local DATA files (> 2 MB) under <dir>; small files
(code, reports, configs) stay. Writes <dir>/ARCHIVED.txt with the remote path, sha256, size and the list of removed files."""
import os, sys, tarfile, hashlib, time
sys.path.insert(0, "/home/moiz/sniper/ops/rec"); import backends as B
d, name = sys.argv[1].rstrip("/"), sys.argv[2]
scratch = "/home/moiz/sniper-data/rec/tmp_archive"; os.makedirs(scratch, exist_ok=True)
tar = f"{scratch}/{name}.tar"
big = []
with tarfile.open(tar, "w") as t:
    for root, _, files in os.walk(d):
        for f in files:
            p = os.path.join(root, f)
            if os.path.islink(p): continue
            t.add(p, arcname=os.path.relpath(p, os.path.dirname(d)))
            if os.path.getsize(p) > 2 * 1024 * 1024: big.append(p)
h = hashlib.sha256()
with open(tar, "rb") as fh:
    for b in iter(lambda: fh.read(1 << 20), b""): h.update(b)
sha, size = h.hexdigest(), os.path.getsize(tar)
be = B.make_backend(log=lambda *a: None) if hasattr(B, "make_backend") else None
if be is None:
    for fn in ("backend_from_env", "get_backend", "from_env"):
        if hasattr(B, fn): be = getattr(B, fn)(log=lambda *a: None); break
be.connect(); be.mkdirs("archive"); rel = f"archive/{name}.tar"
t0 = time.time(); be.upload(tar, rel); up = time.time() - t0
h2 = hashlib.sha256(); be.ftp.retrbinary("RETR " + be._p(rel), h2.update, blocksize=1 << 20)
if h2.hexdigest() != sha or be.size(rel) != size:
    print(f"{name}: VERIFY FAILED, nothing deleted"); sys.exit(1)
freed = 0
for p in big:
    freed += os.path.getsize(p); os.remove(p)
with open(f"{d}/ARCHIVED.txt", "w") as fh:
    fh.write(f"archived {time.strftime('%Y-%m-%d %H:%M')} UTC to ftp FTP_DIR/{rel}\nsha256 {sha}\nsize {size}\nremoved {len(big)} data files (>2 MB), {freed/1e9:.2f} GB; code/reports kept\n")
    fh.writelines(p + "\n" for p in big)
os.remove(tar); be.close()
print(f"{name}: {size/1e9:.2f} GB uploaded in {up:.0f} s, sha256 verified, freed {freed/1e9:.2f} GB ({len(big)} files)")
