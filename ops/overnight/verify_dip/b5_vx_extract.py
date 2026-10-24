#!/usr/bin/env python3
"""verify_dip / vx_extract: independent extractor (own decoder; does not use core/, dip/ or phaseA rows).
Raw collector chunks of one run -> for every launch in that run's launches.jsonl: every pump.fun TradeEvent on that mint in
the first WIN slots after the create (successful AND failed txs, flagged), the CreateEvent (initial reserves, mayhem flag,
quote mint), failed txs touching the mint, and per-slot block-size estimates (max tx index of ANY collected line + 1).
Output: <out>/<tag>/b###.json.gz (per crc32 bucket of the mint) + <out>/<tag>/smax.json.gz + <out>/<tag>/meta.json
usage: python3 -I -B vx_extract.py <run dir> <out dir> <tag> [procs]"""
import base64, binascii, glob, gzip, json, os, struct, sys, zlib, collections, time
from multiprocessing import Pool

TE = bytes([189, 219, 127, 211, 78, 230, 97, 238])     # pump.fun TradeEvent discriminator
CE = bytes([27, 114, 169, 77, 222, 235, 99, 118])      # pump.fun CreateEvent discriminator
A = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
AI = {c: i for i, c in enumerate(A)}
WIN = 720                                              # slots after the create (~153 s)

def b58e(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(A[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))

def b58d(s):
    n = 0
    for c in s: n = n * 58 + AI[c]
    body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + body

def b64(s): return base64.b64decode(s + "=" * (-len(s) % 4))

G = {}
def init(launch_file):
    L = {}
    for l in open(launch_file):
        try: c = json.loads(l)
        except Exception: continue
        if c["mint"] not in L: L[c["mint"]] = c
    G["S"] = {m: c["slot"] for m, c in L.items()}
    G["KEY"] = {b58d(m): m for m in L}
    G["BC"] = {m: c.get("bonding_curve") for m, c in L.items()}

def dec_trade(raw):
    sol, tok = struct.unpack_from("<QQ", raw, 40); buy = raw[56]
    ts, vsol, vtok, rsol, rtok = struct.unpack_from("<qQQQQ", raw, 89)
    fbps = fee = cbps = cfee = None; ixname = None; tflag = None
    if len(raw) >= 225:
        fbps, fee = struct.unpack_from("<QQ", raw, 161); cbps, cfee = struct.unpack_from("<QQ", raw, 209)
    if len(raw) >= 262:
        try:
            nlen = struct.unpack_from("<I", raw, 258)[0]
            if nlen < 64:
                ixname = raw[262:262 + nlen].decode("utf8", "replace")
                if len(raw) > 262 + nlen: tflag = raw[262 + nlen]
        except struct.error: pass
    return sol, tok, buy, vsol, vtok, rsol, rtok, fbps, fee, cbps, cfee, ixname, tflag, len(raw)

def dec_create(raw):
    o = 8
    for _ in range(3):
        n = struct.unpack_from("<I", raw, o)[0]; o += 4 + n
    mint = raw[o:o + 32]; o += 128
    ts, vtok0, vsol0, rtok0, sup = struct.unpack_from("<qQQQQ", raw, o); o += 40
    rest = raw[o + 32:]
    may = rest[0] if len(rest) > 0 else None
    quote = b58e(rest[2:34]) if len(rest) >= 34 else None
    return mint, dict(vtok0=vtok0, vsol0=vsol0, rtok0=rtok0, supply=sup, may=may, quote=quote, evlen=len(raw))

def work(path):
    S = G["S"]; KEY = G["KEY"]; BC = G["BC"]
    smax = {}; trades = collections.defaultdict(list); failed = collections.defaultdict(list); creates = {}
    n = 0; bad = 0; trunc = None; te_err = 0; te_short = 0
    try:
        with gzip.open(path, "rt") as fh:
            for line in fh:
                n += 1
                try: o = json.loads(line)
                except Exception: bad += 1; continue
                s = o.get("s"); i = o.get("i")
                if s is None or i is None: continue
                if i > smax.get(s, -1): smax[s] = i
                err = 1 if o.get("err") else 0
                evs = o.get("ev") or []
                hit = set(); k = 0
                for e in evs:
                    if e.startswith("vdt/007m"):
                        try: raw = b64(e)
                        except (binascii.Error, ValueError): continue
                        if raw[:8] != TE or len(raw) < 129: continue
                        kk = k; k += 1
                        m = KEY.get(raw[8:40])
                        if m is None or s > S[m] + WIN or s < S[m]: continue
                        d = dec_trade(raw)
                        if err: te_err += 1
                        if d[-1] < 225: te_short += 1
                        hit.add(m)
                        bc = BC.get(m); bcp = None
                        for x in o.get("tb") or []:
                            if x and x[0] == m and x[1] == bc: bcp = (x[2], x[3]); break
                        signers = o.get("signers") or [""]
                        trades[m].append([s, i, kk, o.get("sig"), err, signers[0], b58e(raw[57:89])] + list(d) +
                                         [bcp, o.get("bt"), o.get("fee"), o.get("cup"), sum(t[1] for t in (o.get("tips") or []) if isinstance(t, list) and len(t) > 1)])
                    elif e.startswith("G3KpTd7r"):
                        try: raw = b64(e)
                        except (binascii.Error, ValueError): continue
                        if raw[:8] != CE: continue
                        try: mk, cd = dec_create(raw)
                        except (struct.error, IndexError): continue
                        m = KEY.get(mk)
                        if m is not None:
                            cd.update(s=s, i=i, sig=o.get("sig"), err=err); creates.setdefault(m, cd)
                if err:
                    for m in o.get("mints") or []:
                        if m in S and m not in hit and S[m] <= s <= S[m] + WIN:
                            failed[m].append([s, i, (o.get("signers") or [""])[0], [x for x in (o.get("ixn") or []) if "uy" in x or "ell" in x][:3]])
    except (EOFError, zlib.error, OSError) as ex:
        trunc = repr(ex)
    return os.path.basename(path), dict(trades), dict(failed), creates, smax, dict(lines=n, bad=bad, trunc=trunc, te_err=te_err, te_short=te_short)

def bucket(m): return zlib.crc32(m.encode()) % 256

def main():
    run, out, tag = sys.argv[1], sys.argv[2], sys.argv[3]; procs = int(sys.argv[4]) if len(sys.argv) > 4 else 8
    od = os.path.join(out, tag); os.makedirs(od, exist_ok=True)
    files = sorted(glob.glob(os.path.join(run, "txs", "txs_*.jsonl.gz")))
    lf = os.path.join(run, "launches.jsonl")
    T = collections.defaultdict(list); F = collections.defaultdict(list); C = {}; SM = {}; meta = []; t0 = time.time()
    with Pool(procs, initializer=init, initargs=(lf,)) as pool:
        for k, (fn, tr, fa, cr, sm, mt) in enumerate(pool.imap_unordered(work, files), 1):
            for m, v in tr.items(): T[m].extend(v)
            for m, v in fa.items(): F[m].extend(v)
            for m, v in cr.items(): C.setdefault(m, v)
            for s, i in sm.items():
                if i > SM.get(s, -1): SM[s] = i
            mt["file"] = fn; meta.append(mt)
            if k % 10 == 0: print(f"{k}/{len(files)} files {time.time() - t0:.0f}s trades {sum(len(v) for v in T.values())}", flush=True)
    B = collections.defaultdict(dict)
    for m in set(T) | set(C):
        B[bucket(m)][m] = dict(t=sorted(T.get(m, []), key=lambda r: (r[0], r[1], r[2])), f=sorted(F.get(m, [])), c=C.get(m))
    for b in range(256):
        with gzip.open(os.path.join(od, f"b{b:03d}.json.gz"), "wt", compresslevel=3) as f: json.dump(B.get(b, {}), f)
    with gzip.open(os.path.join(od, "smax.json.gz"), "wt") as f: json.dump({str(s): i for s, i in SM.items()}, f)
    json.dump(sorted(meta, key=lambda x: x["file"]), open(os.path.join(od, "meta.json"), "w"), indent=0)
    print("DONE", tag, "mints", len(T), "trades", sum(len(v) for v in T.values()), "creates", len(C), "slots", len(SM),
          "te_err", sum(x["te_err"] for x in meta), "te_short", sum(x["te_short"] for x in meta), "trunc", [x["file"] for x in meta if x["trunc"]], flush=True)

if __name__ == "__main__":
    main()
