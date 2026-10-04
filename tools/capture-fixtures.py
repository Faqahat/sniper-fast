#!/usr/bin/env python3
"""capture-fixtures: build and check the offline fixtures under testdata/ (PLAN WP-00b; WP-09 adds its own modes).

Standard library only. Run from anywhere; paths default to this checkout's testdata/.

Modes (exactly one per call):
  --wallet             Fetch every signature named in testdata/legacy/signatures.json with getTransaction
                       (encoding base64, JSON meta, maxSupportedTransactionVersion 0, commitment finalized) into
                       testdata/wallet/<sig>.json. Each file is the RPC `result` object, re-serialized with sorted keys.
                       Read-only. Files already present are kept unless --refetch.
  --discover           Read-only completeness check of the `landed` list: getSignatureStatuses (searchTransactionHistory)
                       over every copy signature in the raw attempts of the `landed.segments`, compared with the list.
                       Prints the difference; exit 1 if any landed copy is missing from the list or vice versa.
  --pool-bots DIR      Rebuild testdata/legacy/pool-bots.json from the patterns scans DIR/scan-w5h-p*.json
                       (Cherry: /root/arb-lab/tmp-patterns/). Same rule as tools/analysis/patterns/analyze.py:32.
  --wins RUNS          Rebuild testdata/legacy/wins/<seg>/{outcomes,attempts}.jsonl.xz: the verbatim v1 lines of the
                       wins listed in signatures.json `wins_w5h2_w5h3`, for segments that have no full copy in raw/.
                       RUNS is an arb-lab runs directory (RUNS/<seg>/outcomes.jsonl).
  --exec-slice ZST     Rebuild testdata/legacy/exec/<seg>.slice.jsonl.xz (--seg, default w5h-p10): the exec.jsonl v1 lines
                       of the slots around that segment's landed attempts (trigger slot .. landed slot + 1).
                       Decompresses with `zstd -dc` if installed, else node's zlib.createZstdDecompress.
  --manifest           Rewrite testdata/legacy/fixtures.sha256 over every fixture file in testdata/legacy and testdata/wallet.
  --verify             Offline check (CI): every file listed in fixtures.sha256 exists and matches; no fixture is unlisted;
                       raw.sha256 agrees; every signature in signatures.json has its wallet file. Exit 1 on any problem.

RPC (only --wallet and --discover use it): --rpc-url URL (default: the public mainnet endpoint), or --rpc-url-env NAME
to read the URL from an environment variable. A URL read from the environment is never printed or written.
"""
import argparse
import base64
import glob
import hashlib
import json
import lzma
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTDATA = os.path.join(REPO, "testdata")
LEGACY = os.path.join(TESTDATA, "legacy")
WALLET_DIR = os.path.join(TESTDATA, "wallet")
SIGNATURES = os.path.join(LEGACY, "signatures.json")
MANIFEST = os.path.join(LEGACY, "fixtures.sha256")
PUBLIC_RPC = "https://api.mainnet-beta.solana.com"
# Files that are documentation or code, not fixtures: not hashed, ignored by the unlisted check.
NOT_FIXTURES = re.compile(r"(^|/)(README\.md|[^/]*\.py|__pycache__(/.*)?|fixtures\.sha256)$")
# The secret patterns checked before any record line is copied into the repository (as for raw/, README.md).
SECRET = re.compile(r"(?i)(api[-_]?key|apikey|[?&](token|key)=|bearer\s|https?://|wss?://|password|passphrase|secret)")


def die(msg):
    print(f"capture-fixtures: {msg}", file=sys.stderr)
    sys.exit(1)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, obj):
    """Fixture JSON: UTF-8, two-space indent, keys in the order given, trailing newline."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def write_xz(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(lzma.compress(data, preset=9))


def load_signatures():
    with open(SIGNATURES) as f:
        return json.load(f)


def all_sigs(obj):
    """Every value of a "sig" key anywhere in signatures.json, in document order, deduplicated."""
    out, seen = [], set()

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "sig" and isinstance(v, str) and v not in seen:
                    seen.add(v)
                    out.append(v)
                else:
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(obj)
    return out


# ---------------------------------------------------------------- RPC


class Rpc:
    def __init__(self, url, label):
        self.url, self.label, self.calls = url, label, 0

    def call(self, method, params, tries=8):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        for k in range(tries):
            self.calls += 1
            try:
                req = urllib.request.Request(self.url, body, {"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=60) as r:
                    d = json.load(r)
                if "error" in d:
                    print(f"  {method}: rpc error {d['error'].get('code')} {d['error'].get('message', '')[:120]}", file=sys.stderr)
                else:
                    return d["result"]
            except urllib.error.HTTPError as e:
                print(f"  {method}: http {e.code}", file=sys.stderr)
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                print(f"  {method}: {type(e).__name__}", file=sys.stderr)
            time.sleep(min(30, 2 * (k + 1)))
        die(f"{method}: no answer from {self.label} after {tries} tries")


def make_rpc(args):
    if args.rpc_url_env:
        url = os.environ.get(args.rpc_url_env)
        if not url:
            die(f"environment variable {args.rpc_url_env} is not set")
        return Rpc(url, f"${args.rpc_url_env}")
    return Rpc(args.rpc_url, args.rpc_url)


# ---------------------------------------------------------------- --wallet


def cmd_wallet(args):
    sigs = all_sigs(load_signatures())
    rpc = make_rpc(args)
    os.makedirs(WALLET_DIR, exist_ok=True)
    fetched = kept = 0
    for i, sig in enumerate(sigs):
        path = os.path.join(WALLET_DIR, f"{sig}.json")
        if os.path.exists(path) and not args.refetch:
            kept += 1
            continue
        cfg = {"encoding": "base64", "maxSupportedTransactionVersion": 0, "commitment": "finalized"}
        res = None
        for k in range(4):
            res = rpc.call("getTransaction", [sig, cfg])
            if res is not None:
                break
            time.sleep(3 * (k + 1))  # a public node may lack the slot briefly; retry before giving up
        if res is None:
            die(f"getTransaction returned null for {sig}")
        if not (isinstance(res.get("transaction"), list) and res["transaction"][1] == "base64"):
            die(f"{sig}: unexpected transaction encoding")
        with open(path, "w") as f:
            f.write(json.dumps(res, sort_keys=True, separators=(",", ":")) + "\n")
        fetched += 1
        print(f"  [{i + 1}/{len(sigs)}] {sig[:12]} slot {res['slot']}")
        time.sleep(args.sleep)
    print(f"wallet: {len(sigs)} signatures, {fetched} fetched, {kept} kept; {rpc.calls} RPC calls to {rpc.label}")
    if fetched:
        print("run --manifest to update testdata/legacy/fixtures.sha256")


# ---------------------------------------------------------------- --discover


def raw_lines(seg, name):
    p = os.path.join(LEGACY, "raw", seg, f"{name}.jsonl.xz")
    if not os.path.exists(p):
        return []
    with lzma.open(p, "rt") as f:
        return [json.loads(l) for l in f if l.strip()]


def cmd_discover(args):
    s = load_signatures()
    landed = s["landed"]
    copies = {}
    for seg in landed["segments"]:
        for a in raw_lines(seg, "attempts"):
            for c in (a.get("copies") or []) + (a.get("bundle_resends") or []):
                if c.get("sig"):
                    copies.setdefault(c["sig"], (seg, a["attempt"], c.get("path", "resend")))
        for c in raw_lines(seg, "copies"):
            if c.get("sig"):
                copies.setdefault(c["sig"], (seg, c["attempt"], c.get("path")))
    rpc = make_rpc(args)
    sigs = sorted(copies)
    found = {}
    for i in range(0, len(sigs), 256):
        chunk = sigs[i:i + 256]
        res = rpc.call("getSignatureStatuses", [chunk, {"searchTransactionHistory": True}])
        for sig, st in zip(chunk, res["value"]):
            if st is not None:
                found[sig] = st
        time.sleep(args.sleep)
    listed = {r["sig"]: r for r in landed["rows"]}
    missing = sorted(set(found) - set(listed))
    extra = sorted(set(listed) - set(found))
    for sig in missing:
        print(f"MISSING from signatures.json landed: {copies[sig]} {sig} slot {found[sig].get('slot')} err {found[sig].get('err')}")
    for sig in extra:
        print(f"LISTED but no landed copy found: {listed[sig].get('seg')}#{listed[sig].get('attempt')} {sig}")
    print(f"discover: {len(sigs)} copy signatures checked, {len(found)} landed, {len(listed)} listed; "
          f"{len(missing)} missing, {len(extra)} extra; {rpc.calls} RPC calls")
    sys.exit(1 if missing or extra else 0)


# ---------------------------------------------------------------- --pool-bots


def cmd_pool_bots(args):
    files = sorted(glob.glob(os.path.join(args.pool_bots, "scan-w5h-p*.json")), key=lambda p: int(p.rsplit("-p", 1)[1].split(".")[0]))
    if not files:
        die(f"no scan-w5h-p*.json in {args.pool_bots}")
    bots, wins, ours = {}, {}, {}
    for fn in files:
        with open(fn) as f:
            d = json.load(f)
        for p, c in d["pools"].items():
            bots[p] = max(bots.get(p, 0), c.get("bots", 0))  # analyze.py:32 POOLBOTS
            wins[p] = wins.get(p, 0) + c.get("wins", 0)
        for x in d["ours"]:
            for p in x["pools"]:
                a = ours.setdefault(p, [0, 0])
                a[0] += 1
                a[1] += x["verdict"] == "WIN"
    bins = []
    for lo, hi in ((1, 5), (5, 20), (20, 60), (60, 150), (150, None)):
        ps = [p for p in bots if bots[p] >= lo and (hi is None or bots[p] < hi)]
        bins.append({"lo": lo, "hi": hi, "pools": len(ps), "market_wins": sum(wins[p] for p in ps),
                     "our_attempts": sum(ours.get(p, [0, 0])[0] for p in ps), "our_wins": sum(ours.get(p, [0, 0])[1] for p in ps)})
    crowded = sorted((p for p in bots if bots[p] >= 150), key=lambda p: (-bots[p], p))
    out = {
        "schema": "arbx.fixture.pool_bots/1",
        "_doc": ("Per-pool count of distinct arbitrage signers, from the arb-lab patterns scan of w5h-p1..p15 "
                 "(tools/analysis/patterns/scan.py on Cherry, 2026-10-03). bots = the maximum over segments of the number of "
                 "distinct arb signers that touched the pool in one segment (tools/analysis/patterns/analyze.py:32 POOLBOTS). "
                 "`crowded` is the PATTERNS.md item 10 set (bots >= 150), the input of data/crowded-pools.json (PLAN WP-00). "
                 "`bins` reproduces the PATTERNS.md crowding table (pool-attempts: an attempt counts once per pool it touched). "
                 "Rebuild: tools/capture-fixtures.py --pool-bots <dir of scan-w5h-p*.json>."),
        "source": {"producer": "tools/analysis/patterns/scan.py (arb-lab, Cherry /root/arb-lab/tmp-patterns/)",
                   "scanned": "2026-10-03", "copied": "2026-10-04",
                   "files": {os.path.basename(fn): sha256_file(fn) for fn in files}},
        "crowded_min_bots": 150,
        "crowded": [{"pool": p, "bots": bots[p], "market_wins": wins[p], "our_attempts": ours.get(p, [0, 0])[0],
                     "our_wins": ours.get(p, [0, 0])[1]} for p in crowded],
        "bins": bins,
        "pools": {p: bots[p] for p in sorted(bots)},
    }
    path = os.path.join(LEGACY, "pool-bots.json")
    write_json(path, out)
    print(f"pool-bots: {len(bots)} pools from {len(files)} scans, {len(crowded)} with >= 150 bots -> {os.path.relpath(path, REPO)}")


# ---------------------------------------------------------------- --wins


def cmd_wins(args):
    s = load_signatures()
    by_seg = {}
    for r in s["wins_w5h2_w5h3"]["rows"]:
        by_seg.setdefault(r["seg"], set()).add(r["attempt"])
    for seg, atts in sorted(by_seg.items()):
        if os.path.isdir(os.path.join(LEGACY, "raw", seg)):
            continue  # the full v1 files are already in raw/
        for name in ("outcomes", "attempts"):
            src = os.path.join(args.wins, seg, f"{name}.jsonl")
            keep = []
            with open(src, "rb") as f:
                for line in f:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    if row.get("attempt") in atts and (name == "attempts" or row.get("ok") is True):
                        if SECRET.search(line.decode()):
                            die(f"{src}: a kept line matches a secret pattern; not copied")
                        keep.append(line if line.endswith(b"\n") else line + b"\n")
            if len(keep) != len(atts):
                die(f"{src}: expected {len(atts)} lines for attempts {sorted(atts)}, found {len(keep)}")
            dst = os.path.join(LEGACY, "wins", seg, f"{name}.jsonl.xz")
            write_xz(dst, b"".join(keep))
            print(f"wins: {seg} {name} {len(keep)} lines -> {os.path.relpath(dst, REPO)}")


# ---------------------------------------------------------------- --exec-slice

NODE_UNZST = ('const fs=require("fs"),z=require("zlib");process.stdout.on("error",e=>{if(e.code==="EPIPE")process.exit(0);throw e});'
              'fs.createReadStream(process.argv[1]).pipe(z.createZstdDecompress()).pipe(process.stdout);')


def zst_reader(path):
    if shutil.which("zstd"):
        return subprocess.Popen(["zstd", "-dc", path], stdout=subprocess.PIPE)
    if shutil.which("node"):
        return subprocess.Popen(["node", "-e", NODE_UNZST, path], stdout=subprocess.PIPE)
    die("neither zstd nor node is installed")


def cmd_exec_slice(args):
    seg = args.seg
    slots = set()
    for o in raw_lines(seg, "outcomes"):
        if o.get("landed") and o.get("slot"):
            lo = o.get("trigger_slot") or o["slot"]
            slots.update(range(lo, o["slot"] + 2))
    if not slots:
        die(f"no landed outcomes for {seg} in raw/")
    slot_re = re.compile(rb'"slot":(\d+)')
    keep, n = [], 0
    proc = zst_reader(args.exec_slice)
    for line in proc.stdout:
        n += 1
        m = slot_re.search(line)
        if m and int(m.group(1)) in slots:
            if SECRET.search(line.decode(errors="replace")):
                die("an exec line matches a secret pattern; not copied")
            keep.append(line)
    if proc.wait() != 0:
        die("decompression failed")
    dst = os.path.join(LEGACY, "exec", f"{seg}.slice.jsonl.xz")
    write_xz(dst, b"".join(keep))
    print(f"exec-slice: {n} lines read, {len(keep)} kept over {len(slots)} slots {min(slots)}..{max(slots)} -> {os.path.relpath(dst, REPO)}")


# ---------------------------------------------------------------- --manifest / --verify


def fixture_files():
    out = []
    for base in (LEGACY, WALLET_DIR):
        for root, dirs, files in os.walk(base):
            dirs[:] = sorted(d for d in dirs if d != "__pycache__")
            for fn in sorted(files):
                rel = os.path.relpath(os.path.join(root, fn), TESTDATA).replace(os.sep, "/")
                if not NOT_FIXTURES.search(rel):
                    out.append(rel)
    return sorted(out)


def read_manifest(path, base):
    out = {}
    with open(path) as f:
        for line in f:
            if line.strip():
                h, rel = line.rstrip("\n").split("  ", 1)
                out[os.path.normpath(os.path.join(base, rel))] = h
    return out


def cmd_manifest(args):
    files = fixture_files()
    with open(MANIFEST, "w") as f:
        for rel in files:
            f.write(f"{sha256_file(os.path.join(TESTDATA, rel))}  {rel}\n")
    print(f"manifest: {len(files)} files -> {os.path.relpath(MANIFEST, REPO)}")


def cmd_verify(args):
    problems = []
    listed = read_manifest(MANIFEST, TESTDATA)
    for path, h in sorted(listed.items()):
        if not os.path.exists(path):
            problems.append(f"missing: {os.path.relpath(path, TESTDATA)}")
        elif sha256_file(path) != h:
            problems.append(f"sha256 mismatch: {os.path.relpath(path, TESTDATA)}")
    for rel in fixture_files():
        if os.path.normpath(os.path.join(TESTDATA, rel)) not in listed:
            problems.append(f"not in fixtures.sha256: {rel}")
    for path, h in read_manifest(os.path.join(LEGACY, "raw.sha256"), os.path.join(LEGACY, "raw")).items():
        if listed.get(path) != h:
            problems.append(f"raw.sha256 disagrees with fixtures.sha256: {os.path.relpath(path, TESTDATA)}")
    for sig in all_sigs(load_signatures()):
        if not os.path.exists(os.path.join(WALLET_DIR, f"{sig}.json")):
            problems.append(f"no wallet file for {sig}")
    for p in problems:
        print(p)
    print(f"verify: {len(listed)} files listed, {len(problems)} problems")
    sys.exit(1 if problems else 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    m = ap.add_mutually_exclusive_group(required=True)
    m.add_argument("--wallet", action="store_true")
    m.add_argument("--discover", action="store_true")
    m.add_argument("--pool-bots", metavar="DIR")
    m.add_argument("--wins", metavar="RUNS")
    m.add_argument("--exec-slice", metavar="ZST")
    m.add_argument("--manifest", action="store_true")
    m.add_argument("--verify", action="store_true")
    ap.add_argument("--seg", default="w5h-p10", help="segment for --exec-slice")
    ap.add_argument("--rpc-url", default=PUBLIC_RPC)
    ap.add_argument("--rpc-url-env", metavar="NAME")
    ap.add_argument("--refetch", action="store_true", help="--wallet: fetch again even if the file exists")
    ap.add_argument("--sleep", type=float, default=0.4, help="seconds between RPC calls (public endpoint rate limits)")
    args = ap.parse_args()
    if args.wallet:
        cmd_wallet(args)
    elif args.discover:
        cmd_discover(args)
    elif args.pool_bots:
        cmd_pool_bots(args)
    elif args.wins:
        cmd_wins(args)
    elif args.exec_slice:
        cmd_exec_slice(args)
    elif args.manifest:
        cmd_manifest(args)
    else:
        cmd_verify(args)


if __name__ == "__main__":
    main()
