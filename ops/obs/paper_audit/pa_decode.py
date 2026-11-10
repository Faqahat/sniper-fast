#!/usr/bin/env python3
"""PAPER AUDIT tape decode [read-only on the raw recordings]: ops/strategies/presend/real/decode.py's chunk decoder, plus one field per
trade: sh = the first 4 bytes (big-endian u32) of sha256(b"dip" + signature base58) -> the shadow's follower slack
(presend.rs slack_of_sig: SLACK[min(int(sh / 2^32 x 711), 710)]). Everything else is decode.py's (same filters, same layout).
Merge with real/build.py (it keeps every field).
usage: pa_decode.py OUTDIR RECDIR [RECDIR ...] [--min-age 240] [--procs 10]"""
import sys, os, gzip, json, glob, time, hashlib, importlib.util
import numpy as np
from multiprocessing import Pool

_spec = importlib.util.spec_from_file_location("ps_real_decode", "/home/it/sniper/ops/strategies/presend/real/decode.py")
D = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(D)
TDT = np.dtype(D.TDT.descr + [("sh", "u4")])


def sh32(sig): return int.from_bytes(hashlib.sha256(b"dip" + sig.encode()).digest()[:4], "big")


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
                m = D.HEAD.match(line)
                if not m: continue
                nlines += 1
                s, i, bt = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if i > smax.get(s, -1): smax[s] = i
                scnt[s] = scnt.get(s, 0) + 1; sbt[s] = bt
                has_te = D.B64KEY in line
                mine = any(w in line for w in D.WALLETS)
                is_create = '"Create' in line
                if not (has_te or mine or is_create): continue
                r = json.loads(line)
                sg = r.get("signers") or ["?"]
                if mine and any(w in sg for w in D.WALLETS): ours.append(line)
                if r.get("err") is not None: continue
                ixn = r.get("ixn") or []
                if is_create and any(x in ("Create", "CreateV2") for x in ixn):
                    for b in D.chunks_of(r.get("ev")):
                        if b[:8] == D.CREATE_EV:
                            c = D.parse_create(b)
                            c.update(slot=s, idx=i, bt=bt, sig=r["sig"], payer=sg[0], v2=("CreateV2" in ixn), mayhem_ix=("InitializeMayhemState" in ixn))
                            creates.append(c)
                if not has_te: continue
                h = D.sigh(r["sig"]); hs = sh32(r["sig"]); j = 0; sid = gid(sg[0])
                for b in D.chunks_of(r.get("ev")):
                    if b[:8] != D.DISC: continue
                    t = D.parse_trade(b)
                    if t is None: continue
                    mint, sol, tok, buy, user, vsol, vtok, fbps, cbps = t
                    rows.append((s, i, j, gid(mint), gid(user), sid, buy, sol, tok, vsol, vtok, min(fbps, 65535), min(cbps, 65535), h, bt, hs))
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
    args = list(sys.argv[1:])
    min_age = 240; procs = 10
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
