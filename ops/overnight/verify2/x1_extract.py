#!/usr/bin/env python3
"""verify2 / x1: independent extractor (does not use core/ or phaseA rows).
Raw collector chunks -> every tx touching the 238 FINAL-2 pick mints (successful AND failed), with decoded pump.fun
TradeEvents / CreateEvents for those mints. A tx is caught if (a) its "mints" field lists a target, or (b) any of its
events is a TradeEvent/CreateEvent whose mint is a target (decoded from the base64 event itself).
Also records per-slot tx counts (all lines) to detect collector gaps.
Output: work/x1_txs.json.gz  {mint: [tx...]}, work/x1_slots.json.gz, work/x1_meta.json
usage: python3 -I x1_extract.py
"""
import base64, binascii, glob, gzip, json, os, struct, sys, zlib, collections
from multiprocessing import Pool

RAW = "/home/moiz/sniper-data/collect/run_20261022_1543/txs"
LAUNCH = "/home/moiz/sniper-data/collect/run_20261022_1543/launches.jsonl"
PICKS = "/home/moiz/sniper/ops/overnight/core/final2_picks_v3.json"
OUT = "/home/moiz/sniper/ops/overnight/verify2/work"
TE = bytes([189, 219, 127, 211, 78, 230, 97, 238])
CE = bytes([27, 114, 169, 77, 222, 235, 99, 118])
TE64 = '"vdt/007m'           # base64 of TE[:6] (the next char depends on the mint)
CE64 = '"G3KpTd7r'
A = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
AI = {c: i for i, c in enumerate(A)}

def b58e(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(A[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))

def b58d(s):
    n = 0
    for c in s: n = n * 58 + AI[c]
    body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + body

TSTR = None; TKEY = None; BC = None
def init(tstr, bc):
    global TSTR, TKEY, BC
    TSTR = set(tstr); TKEY = {b58d(m): m for m in tstr}; BC = bc

def rstr(b, o):
    n = struct.unpack_from("<I", b, o)[0]
    return b[o + 4:o + 4 + n].decode("utf8", "replace"), o + 4 + n

def dec_trade(b):
    d = dict(mint=b58e(b[8:40]))
    d["sol"], d["tok"] = struct.unpack_from("<QQ", b, 40)
    d["buy"] = b[56]
    d["user"] = b58e(b[57:89])
    d["ts"], d["vsol"], d["vtok"], d["rsol"], d["rtok"] = struct.unpack_from("<qQQQQ", b, 89)
    if len(b) >= 225:
        d["fee_bps"], d["fee"] = struct.unpack_from("<QQ", b, 161)
        d["creator"] = b58e(b[177:209])
        d["cfee_bps"], d["cfee"] = struct.unpack_from("<QQ", b, 209)
    d["evlen"] = len(b)
    return d

def dec_create(b):
    d = {}; o = 8
    d["name"], o = rstr(b, o); d["symbol"], o = rstr(b, o); d["uri"], o = rstr(b, o)
    d["mint"] = b58e(b[o:o + 32]); o += 32
    d["bonding_curve"] = b58e(b[o:o + 32]); o += 32
    d["user"] = b58e(b[o:o + 32]); o += 32
    d["creator"] = b58e(b[o:o + 32]); o += 32
    d["ts"], d["vtok0"], d["vsol0"], d["rtok0"], d["supply"] = struct.unpack_from("<qQQQQ", b, o); o += 40
    rest = b[o:]
    d["token_program"] = b58e(rest[:32]) if len(rest) >= 32 else None
    d["tail"] = rest[32:].hex()
    return d

def b64(s):
    return base64.b64decode(s + "=" * (-len(s) % 4))

def work(path):
    hits = collections.defaultdict(list); slots = collections.Counter(); n = 0; bad = 0; trunc = None
    try:
        with gzip.open(path, "rt") as fh:
            for line in fh:
                n += 1
                # slot of every line (cheap): "s":<num>,
                j = line.find('"s":')
                if j >= 0:
                    k = line.find(",", j)
                    try: slots[int(line[j + 4:k])] += 1
                    except ValueError: pass
                tg = set()
                j = line.find('"mints":[')
                if j >= 0:
                    k = line.find("]", j)
                    for x in line[j + 9:k].split(","):
                        x = x.strip().strip('"')
                        if x in TSTR: tg.add(x)
                for pref in (TE64, CE64):
                    p = line.find(pref)
                    while p >= 0:
                        q = line.find('"', p + 1)
                        s = line[p + 1:q]
                        try:
                            raw = b64(s[:60])
                            if pref == TE64:
                                m = TKEY.get(raw[8:40])
                                if m: tg.add(m)
                            else:
                                full = b64(s); d = dec_create(full)
                                if d["mint"] in TSTR: tg.add(d["mint"])
                        except (binascii.Error, struct.error, ValueError, IndexError): pass
                        p = line.find(pref, q + 1)
                if not tg: continue
                try: o = json.loads(line)
                except Exception: bad += 1; continue
                evs = []
                for kk, e in enumerate(o.get("ev") or []):
                    try: raw = b64(e)
                    except binascii.Error: continue
                    if raw[:8] == TE and len(raw) >= 129:
                        d = dec_trade(raw)
                        if d["mint"] in tg: d["k"] = kk; d["kind"] = "T"; evs.append(d)
                    elif raw[:8] == CE:
                        try: d = dec_create(raw)
                        except Exception: continue
                        if d["mint"] in tg: d["k"] = kk; d["kind"] = "C"; evs.append(d)
                rec = dict(s=o.get("s"), i=o.get("i"), bt=o.get("bt"), sig=o.get("sig"), err=(json.dumps(o["err"]) if o.get("err") else None),
                           fee=o.get("fee"), cu=o.get("cu"), cup=o.get("cup"), cul=o.get("cul"), signers=o.get("signers"), progs=o.get("progs"),
                           ixn=o.get("ixn"), tips=o.get("tips"), mints=o.get("mints"), nev=len(o.get("ev") or []), file=os.path.basename(path))
                for m in tg:
                    r = dict(rec); r["ev"] = [d for d in evs if d["mint"] == m]
                    r["tb"] = [x for x in (o.get("tb") or []) if x and x[0] == m]          # token balance rows of this mint
                    r["sd_bc"] = [x for x in (o.get("sd") or []) if x and x[0] == BC.get(m)]  # SOL delta of the bonding curve
                    hits[m].append(r)
    except (EOFError, zlib.error, OSError) as ex:
        trunc = repr(ex)
    return path, dict(hits), dict(slots), n, bad, trunc

def main():
    picks = json.load(open(sys.argv[1] if len(sys.argv) > 1 else PICKS)); S = set(picks); L = {}
    tag = sys.argv[2] if len(sys.argv) > 2 else "x1"
    for l in open(LAUNCH):
        try: c = json.loads(l)
        except Exception: continue
        if c["mint"] in S and c["mint"] not in L: L[c["mint"]] = c
    bts = sorted(c["bt"] for c in L.values())
    lo, hi = bts[0] - 310, bts[-1] + 160
    files = sorted(f for f in glob.glob(os.path.join(RAW, "txs_*.jsonl.gz")) if lo <= int(os.path.basename(f)[4:-9]) <= hi)
    print("files", len(files), os.path.basename(files[0]), "->", os.path.basename(files[-1]), "targets", len(S), flush=True)
    per = collections.defaultdict(list); slots = collections.Counter(); meta = []
    bc = {m: L[m].get("bonding_curve") for m in L}
    with Pool(6, initializer=init, initargs=(sorted(S), bc)) as pool:
        for path, hits, sc, n, bad, trunc in pool.imap_unordered(work, files):
            for m, v in hits.items(): per[m].extend(v)
            slots.update(sc)
            meta.append(dict(file=os.path.basename(path), lines=n, bad=bad, trunc=trunc, slot_min=min(sc) if sc else None, slot_max=max(sc) if sc else None))
            print("  ", os.path.basename(path), n, "lines", "bad", bad, "trunc", trunc, flush=True)
    for m in per: per[m].sort(key=lambda r: (r["s"], r["i"]))
    with gzip.open(os.path.join(OUT, f"{tag}_txs.json.gz"), "wt") as f: json.dump(per, f)
    if tag == "x1":
        with gzip.open(os.path.join(OUT, "x1_slots.json.gz"), "wt") as f: json.dump({str(k): v for k, v in sorted(slots.items())}, f)
        json.dump(sorted(meta, key=lambda x: x["file"]), open(os.path.join(OUT, "x1_meta.json"), "w"), indent=0)
    print("done: mints with txs", len(per), "txs", sum(len(v) for v in per.values()), flush=True)

if __name__ == "__main__":
    main()
