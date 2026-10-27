#!/usr/bin/env python3
"""REAL replay, step 1 (read-only on the raw recordings): decode every txs_*.jsonl.gz chunk into one .npz.
Based on ops/dip/vm1/decode.py (its TradeEvent layout and line filter), plus: the tx's first signer for every trade, the
creates (CreateEvent: mint, creator, user, mayhem / cashback / holder flags, CreateV2 or legacy), and our two live wallets'
txs (filled AND failed). Only successful txs carry trades (failed txs' events are rolled back).
  trades : slot idx j mint user signer buy sol tok vsol vtok fee_bps cfee_bps sigh bt   (mint/user/signer = file-local ids)
  creates: per create tx (json lines)
  slots  : slot, max tx index seen, records, block time
  ours   : raw JSON lines of our wallets' txs
A chunk younger than --min-age seconds (still being copied) is skipped; a truncated gzip keeps what was read and is marked.
Usage: decode.py OUTDIR RECDIR [RECDIR ...] [--min-age 240] [--procs 14]"""
import sys, os, gzip, json, base64, glob, re, struct, hashlib, time
import numpy as np
from multiprocessing import Pool

DISC = bytes.fromhex("bddb7fd34ee661ee")                     # pump.fun TradeEvent
CREATE_EV = hashlib.sha256(b"event:CreateEvent").digest()[:8]
CPI = bytes.fromhex("e445a52e51cb9a1d")
B64KEY = "vdt/007mY"
WALLETS = ("2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR")   # FRA, AMS (public keys)
HEAD = re.compile(r'\{"s":(\d+),"i":(\d+),"bt":(\d+)')
A58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
TDT = np.dtype([("slot", "u8"), ("idx", "u4"), ("j", "u1"), ("mint", "u4"), ("user", "u4"), ("signer", "u4"), ("buy", "u1"),
                ("sol", "u8"), ("tok", "u8"), ("vsol", "u8"), ("vtok", "u8"), ("fee_bps", "u2"), ("cfee_bps", "u2"), ("sigh", "u8"), ("bt", "u4")])

def b58(b):
    n = int.from_bytes(b, "big"); s = ""
    while n:
        n, r = divmod(n, 58); s = A58[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s

def sigh(sig): return int.from_bytes(hashlib.blake2b(sig.encode(), digest_size=8).digest(), "little")

def parse_trade(b):
    if len(b) < 225: return None
    o = 8
    mint = b58(b[o:o + 32]); o += 32
    sol, tok = struct.unpack_from("<QQ", b, o); o += 16
    buy = b[o]; o += 1
    user = b58(b[o:o + 32]); o += 32
    o += 8
    vsol, vtok, rsol, rtok = struct.unpack_from("<QQQQ", b, o); o += 32
    o += 32
    fee_bps, _ = struct.unpack_from("<QQ", b, o); o += 16
    o += 32
    cfee_bps, _ = struct.unpack_from("<QQ", b, o)
    return mint, sol, tok, buy, user, vsol, vtok, fee_bps, cfee_bps

class Rd:
    def __init__(s, b, o=0): s.b, s.o = b, o
    def u8(s): v = s.b[s.o]; s.o += 1; return v
    def u64(s): v = int.from_bytes(s.b[s.o:s.o + 8], "little"); s.o += 8; return v
    def pk(s): v = b58(s.b[s.o:s.o + 32]); s.o += 32; return v
    def st(s):
        n = int.from_bytes(s.b[s.o:s.o + 4], "little"); s.o += 4
        v = s.b[s.o:s.o + n].decode("utf8", "replace"); s.o += n; return v
    def left(s): return len(s.b) - s.o

def parse_create(raw):
    r = Rd(raw, 8); e = {}
    try:
        r.st(); r.st(); r.st()
        e["mint"], _bc, e["user"], e["creator"] = r.pk(), r.pk(), r.pk(), r.pk()
        r.o += 8
        e["vtok"], e["vsol"], _rt, _sup = r.u64(), r.u64(), r.u64(), r.u64()
        if r.left() >= 32: r.o += 32
        e["mayhem"] = bool(r.u8()) if r.left() >= 1 else False
        e["cashback"] = bool(r.u8()) if r.left() >= 1 else False
        if r.left() >= 32: e["quote"] = r.pk()
        if r.left() >= 8: r.o += 8
        e["cfee_bps"] = r.u64() if r.left() >= 8 else 0
        e["holder"] = bool(r.u8()) if r.left() >= 1 else False
    except Exception as ex:
        e["err"] = str(ex)[:60]
    return e

def chunks_of(line_ev):
    for e in line_ev or []:
        for ch in e.split(" "):
            try: b = base64.b64decode(ch + "=" * (-len(ch) % 4))
            except Exception: continue
            if b[:8] == CPI: b = b[8:]
            yield b

def one(args):
    fn, outdir = args
    out = os.path.join(outdir, os.path.basename(os.path.dirname(os.path.dirname(fn))) + "__" + os.path.basename(fn).replace(".jsonl.gz", ".npz"))
    if os.path.exists(out): return out, "cached"
    rows, ids, idl = [], {}, []
    def gid(k):
        v = ids.get(k)
        if v is None: v = ids[k] = len(idl); idl.append(k)
        return v
    smax, scnt, sbt = {}, {}, {}
    ours, creates = [], []
    nlines = 0; truncated = False
    try:
        with gzip.open(fn, "rt") as f:
            for line in f:
                m = HEAD.match(line)
                if not m: continue
                nlines += 1
                s, i, bt = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if i > smax.get(s, -1): smax[s] = i
                scnt[s] = scnt.get(s, 0) + 1; sbt[s] = bt
                has_te = B64KEY in line
                mine = any(w in line for w in WALLETS)
                is_create = '"Create' in line
                if not (has_te or mine or is_create): continue
                r = json.loads(line)
                sg = r.get("signers") or ["?"]
                if mine and any(w in sg for w in WALLETS): ours.append(line)
                if r.get("err") is not None: continue
                ixn = r.get("ixn") or []
                if is_create and any(x in ("Create", "CreateV2") for x in ixn):
                    for b in chunks_of(r.get("ev")):
                        if b[:8] == CREATE_EV:
                            c = parse_create(b)
                            c.update(slot=s, idx=i, bt=bt, sig=r["sig"], payer=sg[0], v2=("CreateV2" in ixn), mayhem_ix=("InitializeMayhemState" in ixn))
                            creates.append(c)
                if not has_te: continue
                h = sigh(r["sig"]); j = 0; sid = gid(sg[0])
                for b in chunks_of(r.get("ev")):
                    if b[:8] != DISC: continue
                    t = parse_trade(b)
                    if t is None: continue
                    mint, sol, tok, buy, user, vsol, vtok, fbps, cbps = t
                    rows.append((s, i, j, gid(mint), gid(user), sid, buy, sol, tok, vsol, vtok, min(fbps, 65535), min(cbps, 65535), h, bt))
                    j += 1
    except (EOFError, OSError, ValueError) as ex:
        truncated = repr(ex)[:80]
    tr = np.array(rows, dtype=TDT)
    ks = np.array(sorted(smax), dtype=np.uint64)
    sl = np.zeros(len(ks), dtype=[("slot", "u8"), ("maxi", "u4"), ("n", "u4"), ("bt", "u4")])
    sl["slot"] = ks; sl["maxi"] = [smax[k] for k in ks]; sl["n"] = [scnt[k] for k in ks]; sl["bt"] = [sbt[k] for k in ks]
    tmp = out + ".tmp.npz"
    np.savez(tmp, trades=tr, slots=sl, ids=np.array(idl, dtype=object), ours=np.array(ours, dtype=object),
             creates=np.array([json.dumps(c) for c in creates], dtype=object),
             meta=np.array([json.dumps({"file": fn, "lines": nlines, "truncated": truncated})], dtype=object))
    os.replace(tmp, out)
    return out, f"{nlines} lines {len(tr)} trades {len(creates)} creates {len(ours)} ours trunc={truncated}"

if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    min_age = 240; procs = 14
    if "--min-age" in args: k = args.index("--min-age"); min_age = int(args[k + 1]); del args[k:k + 2]
    if "--procs" in args: k = args.index("--procs"); procs = int(args[k + 1]); del args[k:k + 2]
    outdir = args[0]; os.makedirs(outdir, exist_ok=True)
    now = time.time(); files = []
    for rec in args[1:]:
        fs = sorted(glob.glob(os.path.join(rec, "txs", "txs_*.jsonl.gz")))
        files += [f for f in fs if now - os.path.getmtime(f) > min_age]
    t0 = time.time()
    with Pool(procs) as p:
        for k, (o, msg) in enumerate(p.imap_unordered(one, [(f, outdir) for f in files])):
            if k % 50 == 0 or ("trunc=False" not in msg and msg != "cached"):
                print(k, os.path.basename(o), msg, f"{time.time() - t0:.0f}s", flush=True)
    print("DONE", len(files), f"{time.time() - t0:.0f}s", flush=True)
