#!/usr/bin/env python3
"""grad agent, step 1: decode raw recorder chunks into compact per-chunk npz (read-only on recordings).
Per chunk keeps:
  tr  : pump.fun curve TradeEvents with vsol_after >= VMIN (default 45 SOL) -- everything near graduation
  ps  : PumpSwap BuyEvent / SellEvent (all)
  mig : MigrateV2 txs (CreatePoolEvent: mint -> pool, pool opening reserves)
  cmp : pump CompleteEvent (curve complete)  [mint, slot, idx]
  cr  : creates (mint, slot, mayhem flag, creator)
  mx  : per-mint max vsol seen in this chunk for ALL mints (to know which mints ever got near)
  slots: slots present (gap check)
Usage: g1_decode.py OUTDIR CHUNK.jsonl.gz [...] [--procs N]"""
import sys, os, gzip, json, base64, re, struct, hashlib
import numpy as np
from multiprocessing import Pool

TE = bytes.fromhex("bddb7fd34ee661ee"); CPI = bytes.fromhex("e445a52e51cb9a1d")
BUYE = bytes.fromhex("67f4521f2cf57777"); SELLE = bytes.fromhex("3e2f370aa503dc2a")
CPE = bytes.fromhex("b1310cd2a076a774"); CMPE = bytes.fromhex("5f72619cd42e9808")
CRE = hashlib.sha256(b"event:CreateEvent").digest()[:8]
HEAD = re.compile(r'\{"s":(\d+),"i":(\d+),"bt":(\d+),"sig":"([^"]+)","err":(null|)')
EVR = re.compile(r'"ev":\[([^\]]*)\]')
SIGR = re.compile(r'"signers":\["([^"]+)"')
A58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
VMIN = 45_000_000_000
KEEP = set(open(os.environ["GRAD_KEEP"]).read().split()) if os.environ.get("GRAD_KEEP") else None   # full-depth mode: all trades of these mints only

def b58(b):
    n = int.from_bytes(b, "big"); s = ""
    while n:
        n, r = divmod(n, 58); s = A58[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s

TRD = np.dtype([("slot", "u8"), ("idx", "u2"), ("j", "u1"), ("mint", "u4"), ("user", "u4"), ("signer", "u4"), ("buy", "u1"),
                ("sol", "u8"), ("tok", "u8"), ("vsol", "u8"), ("vtok", "u8"), ("rtok", "u8"), ("fbps", "u2"), ("cbps", "u2"), ("bt", "u4"), ("sigh", "u8")])
PSD = np.dtype([("slot", "u8"), ("idx", "u2"), ("j", "u1"), ("pool", "u4"), ("user", "u4"), ("signer", "u4"), ("buy", "u1"),
                ("base", "u8"), ("quote", "u8"), ("pbase", "u8"), ("pquote", "u8"), ("lpfee", "u8"), ("pfee", "u8"), ("ccfee", "u8"),
                ("uquote", "u8"), ("bt", "u4"), ("sigh", "u8"), ("txmint", "u4")])

def sigh(sig): return int.from_bytes(hashlib.blake2b(sig.encode(), digest_size=8).digest(), "little")

def chunks(evs):
    for ch in evs:
        try: b = base64.b64decode(ch + "=" * (-len(ch) % 4))
        except Exception: continue
        if b[:8] == CPI: b = b[8:]
        yield b

def one(args):
    fn, outdir = args
    run = os.path.basename(os.path.dirname(os.path.dirname(fn)))
    out = os.path.join(outdir, run + "__" + os.path.basename(fn).replace(".jsonl.gz", ".npz"))
    if os.path.exists(out): return out, "cached"
    ids, idl = {}, []
    def gid(k):
        v = ids.get(k)
        if v is None: v = ids[k] = len(idl); idl.append(k)
        return v
    tr, ps, mig, cmp_, cr = [], [], [], [], []
    mx = {}; slots = {}
    n = 0; trunc = False
    try:
        with gzip.open(fn, "rt") as f:
            for line in f:
                m = HEAD.match(line)
                if not m: continue
                n += 1
                s, i, bt = int(m.group(1)), int(m.group(2)), int(m.group(3))
                o_ = slots.get(s)
                slots[s] = (bt, i if o_ is None or i > o_[1] else o_[1])
                if m.group(5) != "null": continue           # failed tx: no state change
                has_ps = "pAMMBay6" in line
                has_te = "vdt/007mY" in line
                is_mig = "MigrateV2" in line or '"Migrate"' in line
                is_cr = '"Create' in line
                if not (has_ps or has_te or is_mig or is_cr): continue
                em = EVR.search(line)
                if not em: continue
                evs = [x.strip('"') for x in em.group(1).split('","')] if em.group(1) else []
                sg = SIGR.search(line); signer = gid(sg.group(1)) if sg else 0
                sh = sigh(m.group(4))
                txmint = 0
                if has_ps:
                    mm = re.search(r'"mints":\["([^"]+)"', line); txmint = gid(mm.group(1)) if mm else 0
                j = 0
                for b in chunks(evs):
                    d = b[:8]
                    if d == TE and len(b) >= 225:
                        mint = b[8:40]; sol, tok = struct.unpack_from("<QQ", b, 40); buy = b[56]
                        user = b[57:89]
                        vsol, vtok, rsol, rtok = struct.unpack_from("<QQQQ", b, 97)
                        fbps, = struct.unpack_from("<Q", b, 161); cbps, = struct.unpack_from("<Q", b, 209)
                        mk = b58(mint)
                        if vsol > mx.get(mk, 0): mx[mk] = vsol
                        if (KEEP is None and vsol >= VMIN) or (KEEP is not None and mk in KEEP):
                            tr.append((s, i, j, gid(mk), gid(b58(user)), signer, buy, sol, tok, vsol, vtok, rtok, min(fbps, 65535), min(cbps, 65535), bt, sh))
                        j += 1
                    elif (d == BUYE or d == SELLE) and len(b) >= 8 + 8 * 14 + 32 * 7 + 16:
                        v = struct.unpack_from("<q13Q", b, 8)
                        o = 8 + 8 * 14
                        pool = b58(b[o:o + 32]); user = b58(b[o + 32:o + 64])
                        cc_bps, ccfee = struct.unpack_from("<QQ", b, o + 32 * 7)
                        # v: ts, base_amt, limit, ubase, uquote, pbase, pquote, quote_amt, lpbps, lpfee, pbps, pfee, q_with/without_lp, user_quote
                        if KEEP is None: ps.append((s, i, j, gid(pool), gid(user), signer, 1 if d == BUYE else 0, v[1], v[7], v[5], v[6], v[9], v[11], ccfee,
                                   v[13], bt, sh, txmint))
                        j += 1
                    elif d == CPE and len(b) >= 300:
                        o = 8 + 10
                        bm = b58(b[o + 32:o + 64]); qm = b58(b[o + 64:o + 96]); o += 98
                        vv = struct.unpack_from("<7Q", b, o); o += 57
                        pool = b58(b[o:o + 32])
                        mig.append(dict(slot=s, idx=i, bt=bt, mint=bm, quote=qm, pool=pool, pbase=vv[2], pquote=vv[3], sig=m.group(4),
                                        mig=is_mig))
                    elif d == CMPE:
                        # CompleteEvent: user, mint, bonding_curve, timestamp
                        cmp_.append(dict(slot=s, idx=i, bt=bt, mint=b58(b[40:72]), sig=m.group(4)))
                    elif d == CRE:
                        try:
                            o = 8
                            for _ in range(3):
                                ln = int.from_bytes(b[o:o + 4], "little"); o += 4 + ln
                            mint = b58(b[o:o + 32]); creator = b58(b[o + 96:o + 128]); o += 128 + 8 + 32
                            if len(b) - o >= 32: o += 32
                            may = bool(b[o]) if len(b) > o else False
                            cr.append(dict(slot=s, idx=i, bt=bt, mint=mint, creator=creator, mayhem=may, sig=m.group(4)))
                        except Exception:
                            pass
    except (EOFError, OSError, ValueError) as ex:
        trunc = repr(ex)[:80]
    sl = np.array([(k, v[0], v[1]) for k, v in sorted(slots.items())], dtype=np.uint64).reshape(-1, 3)
    tmp = out + ".tmp.npz"
    np.savez_compressed(tmp, tr=np.array(tr, dtype=TRD), ps=np.array(ps, dtype=PSD), ids=np.array(idl, dtype=object),
                        mig=np.array([json.dumps(x) for x in mig], dtype=object), cmp=np.array([json.dumps(x) for x in cmp_], dtype=object),
                        cr=np.array([json.dumps(x) for x in cr], dtype=object),
                        mx=np.array([json.dumps(mx)], dtype=object), slots=sl,
                        meta=np.array([json.dumps(dict(file=fn, lines=n, trunc=trunc))], dtype=object))
    os.replace(tmp, out)
    return out, f"{n} lines tr={len(tr)} ps={len(ps)} mig={len(mig)} cmp={len(cmp_)} cr={len(cr)} trunc={trunc}"

if __name__ == "__main__":
    a = sys.argv[1:]; procs = 6
    if "--procs" in a: k = a.index("--procs"); procs = int(a[k + 1]); del a[k:k + 2]
    outdir = a[0]; os.makedirs(outdir, exist_ok=True)
    files = a[1:]
    import time; t0 = time.time()
    with Pool(procs) as p:
        for k, (o, msg) in enumerate(p.imap_unordered(one, [(f, outdir) for f in files])):
            print(k, os.path.basename(o), msg, f"{time.time() - t0:.0f}s", flush=True)
    print("DONE", len(files), f"{time.time() - t0:.0f}s", flush=True)
