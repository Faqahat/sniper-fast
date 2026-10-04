#!/usr/bin/env python3
"""Scan every blob in the repo's history (all refs) for key material and credentials; used by the pre-push hook.

usage: python3 tools/secret-scan.py [repo]      (exit 1 if a finding is not in tools/secret-scan-allow.txt)

Prints path, blob, kind and a MASKED value only (never a secret). Keypairs (64-number arrays, base58, hex) are confirmed
by ed25519 derivation, so transaction signatures do not match. Allowlist lines: <path> TAB <kind> TAB <value sha10>.
Needs python3 with the `cryptography` package."""
import re, subprocess, sys, hashlib, json
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n = 0
    for c in s: n = n * 58 + B58.index(c)
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b
def b58e(b):
    n = int.from_bytes(b, "big"); s = ""
    while n: n, r = divmod(n, 58); s = B58[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s
def pub_of(seed):
    return Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
def is_keypair(b):
    return len(b) == 64 and pub_of(b[:32]) == b[32:]
def mask(v): return f"{v[:4]}…(len {len(v)}, sha {hashlib.sha256(v.encode()).hexdigest()[:10]})"
import os
repo = sys.argv[1] if len(sys.argv) > 1 else "."
allow_file = os.path.join(repo, "tools", "secret-scan-allow.txt")
allow = set()
if os.path.exists(allow_file):
    for l in open(allow_file):
        l = l.split("#")[0].strip()
        if l: allow.add(tuple(l.split("\t")[:3]))
objs = subprocess.run(["git", "-C", repo, "rev-list", "--objects", "--all"], capture_output=True, text=True).stdout.split("\n")
paths = {}
for l in objs:
    p = l.split(" ", 1)
    if len(p) == 2: paths.setdefault(p[0], p[1])
batch = subprocess.run(["git", "-C", repo, "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)"], input="\n".join(paths), capture_output=True, text=True).stdout.split("\n")
blobs = [(x.split()[0], int(x.split()[2])) for x in batch if x and x.split()[1] == "blob"]
R_ARR = re.compile(r"\[(?:\s*\d{1,3}\s*,){63}\s*\d{1,3}\s*\]")
R_B58 = re.compile(r"(?<![1-9A-HJ-NP-Za-km-z])[1-9A-HJ-NP-Za-km-z]{85,90}(?![1-9A-HJ-NP-Za-km-z])")
R_HEX = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{128}(?![0-9a-fA-F])")
PLACE = re.compile(r"^(\$|<|\{|x{4,}|your|example|changeme|placeholder|redacted|\.\.\.)", re.I)
R_CRED = [
    ("kv-credential", re.compile(r"(?i)(api[-_]?key|apikey|access[-_]?token|auth[-_]?token|x[-_]token|secret[-_]?key|password|passphrase|private[-_]?key)\s*[\"']?\s*[:=]\s*[\"']([^\s\"']{8,})[\"']")),
    ("url-credential", re.compile(r"(?i)[?&](api[-_]?key|apikey|key|token|auth|c)=([A-Za-z0-9\-_.~]{12,})")),
    ("bearer", re.compile(r"Bearer\s+([A-Za-z0-9\-._~+/]{20,})")),
    ("pem-private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----()")),
    ("uuid-near-key", re.compile(r"(?i)(?:key|uuid|auth|token)[^\n]{0,40}?([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")),
    ("landx-path-key", re.compile(r"/txb/([A-Za-z0-9]{8,})")),
    ("keystore-blob", re.compile(r"\"(v[23]:(?:\d+:)?[0-9a-f]{100,})\"")),
]
found = []
for sha, size in blobs:
    path = paths[sha]
    if size > 8_000_000 or path.endswith((".so", ".bin", ".zst", ".png", ".jpg", ".gz")): continue
    t = subprocess.run(["git", "-C", repo, "cat-file", "-p", sha], capture_output=True).stdout.decode("utf-8", "ignore")
    for m in R_ARR.finditer(t):
        b = bytes(int(x) for x in re.findall(r"\d+", m.group(0)))
        if all(x < 256 for x in b) and is_keypair(b): found.append((path, sha[:8], "KEYPAIR-json-array", "pubkey " + b58e(b[32:])))
    for m in R_B58.finditer(t):
        try:
            b = b58d(m.group(0))
            if is_keypair(b): found.append((path, sha[:8], "KEYPAIR-base58", "pubkey " + b58e(b[32:])))
        except Exception: pass
    for m in R_HEX.finditer(t):
        b = bytes.fromhex(m.group(0))
        if is_keypair(b): found.append((path, sha[:8], "KEYPAIR-hex", "pubkey " + b58e(b[32:])))
    for kind, rx in R_CRED:
        for m in rx.finditer(t):
            v = m.group(m.lastindex) if m.lastindex else m.group(0)
            if kind != "pem-private-key" and (not v or PLACE.match(v)): continue
            found.append((path, sha[:8], kind, mask(v) if v else "-"))
seen, bad = set(), 0
for f in sorted(found):
    k = (f[0], f[2], f[3])
    if k in seen: continue
    seen.add(k)
    sha10 = f[3].split("sha ")[-1].rstrip(")") if "sha " in f[3] else f[3]
    ok = (f[0], f[2], sha10) in allow
    bad += not ok
    print(("allowed\t" if ok else "BLOCK\t") + "\t".join(f))
print(f"# scanned {len(blobs)} blobs: {len(seen)} findings, {bad} not allowlisted", file=sys.stderr)
sys.exit(1 if bad else 0)
