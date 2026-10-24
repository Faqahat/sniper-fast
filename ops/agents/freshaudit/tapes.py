#!/usr/bin/env python3
# full trade tapes (ok trades + failed txs) for given (mint, slot_from, slot_to) windows, scanned from raw chunks
# usage: tapes.py <run_dir> <windows.json> <out.json.gz> [procs]
import sys, os, json, gzip, glob, base64, zlib, collections
from multiprocessing import Pool
RUN, WIN, OUTP = sys.argv[1], sys.argv[2], sys.argv[3]
PROCS = int(sys.argv[4]) if len(sys.argv) > 4 else 4
TRADE = bytes([189, 219, 127, 211, 78, 230, 97, 238])
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
TIPMAP = json.load(open("/home/moiz/sniper/ops/agents/tipmap.json"))
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
W = collections.defaultdict(list)
for m, a, b in json.load(open(WIN)): W[m].append((a, b))
SMIN = min(a for v in W.values() for a, b in v); SMAX = max(b for v in W.values() for a, b in v)
def inwin(m, s):
    for a, b in W.get(m, ()):
        if a <= s <= b: return True
    return False
def work(path):
    out = []
    try:
        for line in gzip.open(path, "rt"):
            # cheap prefilter: slot range
            try: s = int(line[5:line.index(",", 5)])
            except Exception: continue
            if s < SMIN or s > SMAX: continue
            r = json.loads(line)
            ms = set(r.get("mints") or [])
            evs = []
            for e in r.get("ev") or []:
                try: raw = base64.b64decode(e + "=" * (-len(e) % 4))
                except Exception: continue
                if raw[:8] != TRADE or len(raw) < 225: continue
                u = lambda o: int.from_bytes(raw[o:o + 8], "little")
                m = b58(raw[8:40]); ms.add(m)
                evs.append([m, raw[56], u(40), u(48), b58(raw[57:89]), u(97), u(105), u(161), u(209)])
            hit = [m for m in ms if inwin(m, s)]
            if not hit: continue
            sg = (r.get("signers") or [None])[0]
            tips = [[TIPMAP.get(a, "?" + a[:6]), int(l)] for a, l in (r.get("tips") or [])]
            err = r.get("err")
            if err:
                ie = err.get("InstructionError") if isinstance(err, dict) else None
                err = (f"{ie[0]}:{ie[1].get('Custom')}" if ie and isinstance(ie[1], dict) and "Custom" in ie[1] else json.dumps(err)[:50])
            for m in hit:
                mev = [e for e in evs if e[0] == m]
                out.append(dict(m=m, s=s, i=r["i"], bt=r.get("bt"), sig=r["sig"], sg=sg, err=err, fee=r.get("fee"), cup=r.get("cup"), tips=tips,
                                ixn=(r.get("ixn") or [])[:6], ev=[e[1:] for e in mev]))
    except (EOFError, OSError, zlib.error): pass
    return out
if __name__ == "__main__":
    fs = sorted(glob.glob(os.path.join(RUN, "txs", "*.jsonl.gz")))
    # keep chunks whose slot range can overlap: chunk names are unix start times; select by a coarse slot->time map
    T = {}
    for m, v in W.items(): pass
    sel = fs[:-1]
    if len(sys.argv) > 6:
        t0, t1 = int(sys.argv[5]), int(sys.argv[6]); sel = [f for f in sel if t0 <= int(os.path.basename(f)[4:14]) <= t1]
    res = collections.defaultdict(list)
    with Pool(PROCS) as p:
        for out in p.imap_unordered(work, sel):
            for r in out: res[r["m"]].append(r)
    for m in res: res[m].sort(key=lambda r: (r["s"], r["i"]))
    json.dump(res, gzip.open(OUTP, "wt"))
    print("DONE", len(sel), "chunks", len(res), "mints", sum(len(v) for v in res.values()), "rows")
