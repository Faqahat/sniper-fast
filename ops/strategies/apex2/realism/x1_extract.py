#!/usr/bin/env python3
"""APEX2 step 1 (read-only on raw collect tape): decode each txs_*.jsonl.gz chunk into one .npz.

Independent decoder (own code; TradeEvent / CreateEvent layouts from the pump.fun IDL, same as ops/dip decoders).
  trades : every TradeEvent of a SUCCESSFUL tx: slot idx j mint user signer buy sol tok vsol vtok rsol rtok fee_bps
           cfee_bps txfee tips cu ixk sd (signer SOL delta, lamports) bt
           ixk bitmask from the tx's ixn: 1 Buy, 2 BuyV3, 4 BuyExactSolIn*, 8 Sell*, 16 Create*, 32 >1 trade ix
  fails  : FAILED txs that name a mint created at most 3 slots earlier (launches.jsonl of the same run):
           slot idx mint signer txfee tips cu ixk
  creates: CreateEvent of successful create txs (+ tx fee, tips, ixn flags)
  slots  : slot, max tx index seen, lines, block time
usage: x1_extract.py OUTDIR RUNDIR [RUNDIR ...] [--procs 3] [--min-age 300]"""
import sys, os, gzip, json, base64, glob, re, struct, hashlib, time
import numpy as np
from multiprocessing import Pool

DISC = bytes.fromhex("bddb7fd34ee661ee")
CREATE_EV = hashlib.sha256(b"event:CreateEvent").digest()[:8]
CPI = bytes.fromhex("e445a52e51cb9a1d")
B64KEY = "vdt/007mY"
HEAD = re.compile(r'\{"s":(\d+),"i":(\d+),"bt":(\d+)')
A58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
TDT = np.dtype([("slot", "u8"), ("idx", "u4"), ("j", "u1"), ("mint", "u4"), ("user", "u4"), ("signer", "u4"), ("buy", "u1"),
                ("sol", "u8"), ("tok", "u8"), ("vsol", "u8"), ("vtok", "u8"), ("rsol", "u8"), ("rtok", "u8"),
                ("fee_bps", "u2"), ("cfee_bps", "u2"), ("txfee", "u4"), ("tips", "u8"), ("cu", "u4"), ("ixk", "u1"),
                ("sd", "i8"), ("bt", "u4")])
FDT = np.dtype([("slot", "u8"), ("idx", "u4"), ("mint", "u4"), ("signer", "u4"), ("txfee", "u4"), ("tips", "u8"),
                ("cu", "u4"), ("ixk", "u1")])
G = {}

def b58(b):
    n = int.from_bytes(b, "big"); s = ""
    while n:
        n, r = divmod(n, 58); s = A58[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s

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
    return mint, sol, tok, buy, user, vsol, vtok, rsol, rtok, fee_bps, cfee_bps

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
        e["name"], e["symbol"], e["uri"] = r.st(), r.st(), r.st()
        e["mint"], _bc, e["user"], e["creator"] = r.pk(), r.pk(), r.pk(), r.pk()
        r.o += 8
        e["vtok"], e["vsol"], e["rtok"], e["supply"] = r.u64(), r.u64(), r.u64(), r.u64()
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

def chunks_of(ev):
    for e in ev or []:
        for ch in e.split(" "):
            try: b = base64.b64decode(ch + "=" * (-len(ch) % 4))
            except Exception: continue
            if b[:8] == CPI: b = b[8:]
            yield b

def ixkind(ixn):
    k = 0; nt = 0
    for x in ixn:
        if x == "Buy": k |= 1; nt += 1
        elif x == "BuyV3": k |= 2; nt += 1
        elif x.startswith("BuyExactSolIn"): k |= 4; nt += 1
        elif x.startswith("Sell"): k |= 8; nt += 1
        elif x in ("Create", "CreateV2"): k |= 16
    if nt > 1: k |= 32
    return k

def one(args):
    fn, outdir, run = args
    out = os.path.join(outdir, run + "__" + os.path.basename(fn).replace(".jsonl.gz", ".npz"))
    if os.path.exists(out): return out, "cached"
    cslot = G["cslot"][run]
    rows, frows, ids, idl, creates = [], [], {}, [], []
    def gid(k):
        v = ids.get(k)
        if v is None: v = ids[k] = len(idl); idl.append(k)
        return v
    smax, scnt, sbt = {}, {}, {}
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
                failed = '"err":null' not in line[:400]
                if failed:
                    if '"mints":["' not in line: continue
                    r = json.loads(line)
                    if r.get("err") is None: failed = False
                    else:
                        ms = r.get("mints") or []
                        mm = None
                        for x in ms:
                            c = cslot.get(x)
                            if c is not None and c <= s <= c + 3: mm = x; break
                        if mm is None: continue
                        sg = r.get("signers") or ["?"]
                        frows.append((s, i, gid(mm), gid(sg[0]), min(int(r.get("fee") or 0), 2**32 - 1),
                                      sum(int(t[1]) for t in (r.get("tips") or [])), int(r.get("cu") or 0), ixkind(r.get("ixn") or [])))
                        continue
                has_te = B64KEY in line; is_create = '"Create' in line
                if not (has_te or is_create): continue
                r = json.loads(line)
                if r.get("err") is not None: continue
                sg = r.get("signers") or ["?"]; ixn = r.get("ixn") or []
                tips = sum(int(t[1]) for t in (r.get("tips") or []))
                txfee = min(int(r.get("fee") or 0), 2**32 - 1)
                if is_create and any(x in ("Create", "CreateV2") for x in ixn):
                    for b in chunks_of(r.get("ev")):
                        if b[:8] == CREATE_EV:
                            c = parse_create(b)
                            c.update(slot=s, idx=i, bt=bt, sig=r["sig"], payer=sg[0], signers=sg, v2=("CreateV2" in ixn),
                                     mayhem_ix=("InitializeMayhemState" in ixn), txfee=txfee, tips=tips, cu=r.get("cu"))
                            creates.append(c)
                if not has_te: continue
                sd0 = 0
                for a, d in (r.get("sd") or []):
                    if a == sg[0]: sd0 = int(d); break
                j = 0; sid = gid(sg[0]); ik = ixkind(ixn); cu = int(r.get("cu") or 0)
                for b in chunks_of(r.get("ev")):
                    if b[:8] != DISC: continue
                    t = parse_trade(b)
                    if t is None: continue
                    mint, sol, tok, buy, user, vsol, vtok, rsol, rtok, fbps, cbps = t
                    rows.append((s, i, j, gid(mint), gid(user), sid, buy, sol, tok, vsol, vtok, rsol, rtok, min(fbps, 65535),
                                 min(cbps, 65535), txfee, tips, cu, ik, sd0, bt))
                    j += 1
    except (EOFError, OSError, ValueError) as ex:
        truncated = repr(ex)[:80]
    tr = np.array(rows, dtype=TDT); fr = np.array(frows, dtype=FDT)
    ks = np.array(sorted(smax), dtype=np.uint64)
    sl = np.zeros(len(ks), dtype=[("slot", "u8"), ("maxi", "u4"), ("n", "u4"), ("bt", "u4")])
    sl["slot"] = ks; sl["maxi"] = [smax[k] for k in ks]; sl["n"] = [scnt[k] for k in ks]; sl["bt"] = [sbt[k] for k in ks]
    tmp = out + ".tmp.npz"
    np.savez(tmp, trades=tr, fails=fr, slots=sl, ids=np.array(idl, dtype=object),
             creates=np.array([json.dumps(c) for c in creates], dtype=object),
             meta=np.array([json.dumps({"file": fn, "lines": nlines, "truncated": truncated})], dtype=object))
    os.replace(tmp, out)
    return out, f"{nlines} lines {len(tr)} trades {len(fr)} fails {len(creates)} creates trunc={truncated}"

def init(cs): G["cslot"] = cs

if __name__ == "__main__":
    a = sys.argv[1:]; procs = 3; min_age = 300
    if "--procs" in a: k = a.index("--procs"); procs = int(a[k + 1]); del a[k:k + 2]
    if "--min-age" in a: k = a.index("--min-age"); min_age = int(a[k + 1]); del a[k:k + 2]
    outdir = a[0]; os.makedirs(outdir, exist_ok=True)
    jobs = []; cs = {}
    for rd in a[1:]:
        rd = rd.rstrip("/"); run = os.path.basename(rd); d = {}
        for l in open(rd + "/launches.jsonl"):
            try: j = json.loads(l); d[j["mint"]] = int(j["slot"])
            except Exception: pass
        cs[run] = d
        for fn in sorted(glob.glob(rd + "/txs/txs_*.jsonl.gz")):
            if time.time() - os.path.getmtime(fn) < min_age: continue
            jobs.append((fn, outdir, run))
    print("jobs", len(jobs), flush=True)
    with Pool(procs, initializer=init, initargs=(cs,)) as P:
        for k, (o, msg) in enumerate(P.imap_unordered(one, jobs)):
            print(k, os.path.basename(o), msg, flush=True)
