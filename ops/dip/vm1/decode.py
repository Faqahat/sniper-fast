#!/usr/bin/env python3
"""VM1 independent check, step 1: my own decoder of the raw recordings (read-only).

For every txs_*.jsonl.gz of a recording it writes one .npz with
  trades : every pump.fun bonding-curve TradeEvent of a SUCCESSFUL tx (failed txs' logs are rolled back, so skipped),
           fields slot, idx (tx index in the block), j (event order inside the tx), mint/user (file-local string ids),
           buy, sol, tok, vsol, vtok (post-trade virtual reserves), rsol, rtok, fee_bps, cfee_bps, sigh (64-bit sig hash), bt
  slots  : per slot: max tx index seen, records seen, block time  (block size estimate for the block clock)
  ours   : raw JSON lines of txs signed by our live wallets (filled AND failed buys/sells, with fee/tips/err)
TradeEvent layout (Anchor event, little-endian), from the pump.fun IDL:
  disc[8] mint[32] sol_amount u64 token_amount u64 is_buy u8 user[32] timestamp i64
  virtual_sol_reserves u64 virtual_token_reserves u64 real_sol_reserves u64 real_token_reserves u64
  fee_recipient[32] fee_basis_points u64 fee u64 creator[32] creator_fee_basis_points u64 creator_fee u64 ...
Usage: decode.py OUTDIR RECDIR [RECDIR ...]
"""
import sys, os, gzip, json, base64, glob, re, struct, hashlib
import numpy as np
from multiprocessing import Pool

DISC = bytes.fromhex("bddb7fd34ee661ee")      # pump.fun TradeEvent
CPI = bytes.fromhex("e445a52e51cb9a1d")       # anchor emit_cpi prefix (handled, in case)
B64KEY = "vdt/007mY"                          # base64 of the discriminator's first 6+ bytes (fast line filter)
WALLETS = ("2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE",   # FRA live wallet
           "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR")   # AMS live wallet
HEAD = re.compile(r'\{"s":(\d+),"i":(\d+),"bt":(\d+)')
A58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
TDT = np.dtype([("slot", "u8"), ("idx", "u4"), ("j", "u1"), ("mint", "u4"), ("user", "u4"), ("buy", "u1"),
                ("sol", "u8"), ("tok", "u8"), ("vsol", "u8"), ("vtok", "u8"), ("rsol", "u8"), ("rtok", "u8"),
                ("fee_bps", "u2"), ("cfee_bps", "u2"), ("sigh", "u8"), ("bt", "u4")])

def b58(b):
    n = int.from_bytes(b, "big"); s = ""
    while n:
        n, r = divmod(n, 58); s = A58[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s

def sigh(sig):
    return int.from_bytes(hashlib.blake2b(sig.encode(), digest_size=8).digest(), "little")

def parse_trade(b):
    """b starts with the TradeEvent discriminator; returns a tuple or None if too short"""
    if len(b) < 8 + 32 + 8 + 8 + 1 + 32 + 8 + 8 * 4 + 32 + 16 + 32 + 16:
        return None
    o = 8
    mint = b58(b[o:o + 32]); o += 32
    sol, tok = struct.unpack_from("<QQ", b, o); o += 16
    buy = b[o]; o += 1
    user = b58(b[o:o + 32]); o += 32
    o += 8                                          # timestamp
    vsol, vtok, rsol, rtok = struct.unpack_from("<QQQQ", b, o); o += 32
    o += 32                                         # fee recipient
    fee_bps, _fee = struct.unpack_from("<QQ", b, o); o += 16
    o += 32                                         # creator
    cfee_bps, _cfee = struct.unpack_from("<QQ", b, o); o += 16
    return mint, sol, tok, buy, user, vsol, vtok, rsol, rtok, fee_bps, cfee_bps

def one(args):
    fn, outdir = args
    out = os.path.join(outdir, os.path.basename(os.path.dirname(os.path.dirname(fn))) + "__" + os.path.basename(fn).replace(".jsonl.gz", ".npz"))
    if os.path.exists(out):
        return out, "cached"
    rows, mints, users, mid, uid = [], [], [], {}, {}
    smax, scnt, sbt = {}, {}, {}
    ours = []
    nlines = 0; truncated = False
    try:
        with gzip.open(fn, "rt") as f:
            for line in f:
                m = HEAD.match(line)
                if not m:
                    continue
                nlines += 1
                s, i, bt = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if i > smax.get(s, -1): smax[s] = i
                scnt[s] = scnt.get(s, 0) + 1; sbt[s] = bt
                has_te = B64KEY in line
                mine = any(w in line for w in WALLETS)
                if not (has_te or mine):
                    continue
                r = json.loads(line)
                if mine and any(w in (r.get("signers") or []) for w in WALLETS):
                    ours.append(line)
                if not has_te or r.get("err") is not None:
                    continue
                h = sigh(r["sig"]); j = 0
                for e in r.get("ev") or []:
                    for ch in e.split(" "):
                        try:
                            b = base64.b64decode(ch)
                        except Exception:
                            continue
                        if b[:8] == CPI:
                            b = b[8:]
                        if b[:8] != DISC:
                            continue
                        t = parse_trade(b)
                        if t is None:
                            continue
                        mint, sol, tok, buy, user, vsol, vtok, rsol, rtok, fbps, cbps = t
                        if mint not in mid: mid[mint] = len(mints); mints.append(mint)
                        if user not in uid: uid[user] = len(users); users.append(user)
                        rows.append((s, i, j, mid[mint], uid[user], buy, sol, tok, vsol, vtok, rsol, rtok, min(fbps, 65535), min(cbps, 65535), h, bt))
                        j += 1
    except (EOFError, OSError, ValueError) as ex:      # a file still being written: keep what is complete
        truncated = repr(ex)[:80]
    tr = np.array(rows, dtype=TDT)
    ks = np.array(sorted(smax), dtype=np.uint64)
    sl = np.zeros(len(ks), dtype=[("slot", "u8"), ("maxi", "u4"), ("n", "u4"), ("bt", "u4")])
    sl["slot"] = ks; sl["maxi"] = [smax[k] for k in ks]; sl["n"] = [scnt[k] for k in ks]; sl["bt"] = [sbt[k] for k in ks]
    tmp = out + ".tmp.npz"
    np.savez(tmp, trades=tr, slots=sl, mints=np.array(mints, dtype=object), users=np.array(users, dtype=object),
             ours=np.array(ours, dtype=object), meta=np.array([json.dumps({"file": fn, "lines": nlines, "truncated": truncated})], dtype=object))
    os.replace(tmp, out)
    return out, f"{nlines} lines {len(tr)} trades {len(ours)} ours trunc={truncated}"

if __name__ == "__main__":
    outdir = sys.argv[1]; os.makedirs(outdir, exist_ok=True)
    files = []
    for rec in sys.argv[2:]:
        files += sorted(glob.glob(os.path.join(rec, "txs", "txs_*.jsonl.gz")))
    with Pool(15) as p:
        for k, (o, msg) in enumerate(p.imap_unordered(one, [(f, outdir) for f in files])):
            if k % 50 == 0 or "trunc=False" not in msg:
                print(k, os.path.basename(o), msg, flush=True)
    print("DONE", len(files))
