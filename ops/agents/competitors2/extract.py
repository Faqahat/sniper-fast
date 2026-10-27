#!/usr/bin/env python3
# competitors2/extract.py -- READ-ONLY. Race universe for the "who beats our dip bot" study (owner 10-24 ~23:30 PKT).
# Every dump our engine logged in runs r5..r10 (FRA) + ams_r9/r10 (deduped by sig) -> every tx on that mint in slots
# S-2 .. S+2 from the collector's raw chunks (R3 run_20261023_1426 + R4 run_20261024_1425, failed txs included),
# as compact rows. One output file per chunk (merge happens in races.py).
# usage: python3 -I extract.py [--workers 3] [--only-new]
# Out: /home/moiz/sniper-data/competitors2/rows/<run>_<chunk>.jsonl.gz  (one line per mint: {"m":mint,"rows":[...]})
import json, os, sys, glob, gzip, base64, subprocess, collections, time
from multiprocessing import Pool
RUNS = "/home/moiz/sniper-data/competitors2/runs"
OUT = "/home/moiz/sniper-data/competitors2/rows"
R3 = "/home/moiz/sniper-data/collect/run_20261023_1426/txs"; R3_END = 1792855576 + 120   # tail end of R3 (+ slack)
R4 = "/home/moiz/sniper-data/collect/run_20261024_1425/txs"; R4_START = 1792851902 - 60
TIP = json.load(open("/home/moiz/sniper/ops/agents/tipmap.json"))
TRADE_DISC = bytes([189, 219, 127, 211, 78, 230, 97, 238])
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58enc(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
W0, W1 = 2, 2          # slots before / after the dump slot to keep

def load_dumps():
    D = {}
    for f in sorted(glob.glob(f"{RUNS}/*.jsonl")):
        for l in open(f):
            if '"dump"' not in l and '"fire"' not in l: continue
            e = json.loads(l)
            if e.get("ev") == "dump": D.setdefault(e["sig"], dict(m=e["mint"], s=e["slot"], t=e["t"] / 1e9))
            elif e.get("ev") == "fire": D.setdefault(e["dump_sig"], dict(m=e["mint"], s=e["slot"], t=e["t_dump_rx"] / 1e9))
    return D

def errc(err):
    if not err: return None
    try:
        ie = err.get("InstructionError")
        if ie:
            c = ie[1]
            if isinstance(c, dict): c = c.get("Custom", next(iter(c)))
            return f"{c}@{ie[0]}"
        return next(iter(err)) if isinstance(err, dict) else str(err)
    except Exception:
        return str(err)[:40]

def compact(r, mint):
    ix = r.get("ixn") or []; ixs = " ".join(ix)
    side = "B" if "Buy" in ixs else ("S" if "Sell" in ixs else ("C" if "Create" in ixs else "O"))
    sg = r.get("signers") or ["?"]
    sd = {a: int(d) for a, d in (r.get("sd") or [])}
    tr = []
    for s in r.get("ev") or []:
        try: raw = base64.b64decode(s + "=" * (-len(s) % 4))
        except Exception: continue
        if raw[:8] != TRADE_DISC or len(raw) < 113: continue
        if b58enc(raw[8:40]) != mint: continue
        u = lambda o: int.from_bytes(raw[o:o + 8], "little")
        tr.append([u(40), u(48), raw[56], b58enc(raw[57:89]), u(97), u(105)])
    tips = [[TIP.get(a, "?" + a[:6]), int(d)] for a, d in (r.get("tips") or [])]
    return dict(s=int(r["s"]), i=int(r["i"]), sig=r["sig"], w=sg[0], ns=len(sg), sg=sg[1:3], side=side, err=errc(r.get("err")),
                fee=r.get("fee"), cu=r.get("cu"), cup=r.get("cup"), cul=r.get("cul"), tips=tips, progs=r.get("progs") or [],
                ixn=ix, tr=tr, sdw=sd.get(sg[0], 0), nm=len(r.get("mints") or []))

def work(arg):
    path, want = arg            # want: mint -> sorted list of dump slots
    name = os.path.basename(os.path.dirname(os.path.dirname(path)))[4:12] + "_" + os.path.basename(path).split("_")[1].split(".")[0]
    outp = f"{OUT}/{name}.jsonl.gz"
    if os.path.exists(outp): return name, -1, 0.0
    t0 = time.time()
    lo = {m: (min(v) - W0, max(v) + W1) for m, v in want.items()}
    slots = {m: set(x for S in v for x in range(S - W0, S + W1 + 1)) for m, v in want.items()}
    acc = collections.defaultdict(dict); n = 0
    p = subprocess.Popen(["zcat", path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=1 << 20)
    for l in p.stdout:
        j = l.find(b'"mints":[')
        if j < 0: continue
        k = l.find(b']', j)
        ms = l[j + 9:k].decode().replace('"', '').split(",")
        hit = [m for m in ms if m in lo]
        if not hit: continue
        s = int(l[5:l.find(b",")])
        hit = [m for m in hit if s in slots[m]]
        if not hit: continue
        try: r = json.loads(l)
        except Exception: continue
        for m in hit:
            acc[m][r["sig"]] = compact(r, m); n += 1
    p.wait()
    tmp = outp + ".tmp"
    with gzip.open(tmp, "wt", compresslevel=3) as f:
        for m, d in acc.items(): f.write(json.dumps(dict(m=m, rows=list(d.values())), separators=(",", ":")) + "\n")
    os.rename(tmp, outp)
    return name, n, time.time() - t0

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    nw = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 3
    D = load_dumps()
    chunks = [(int(os.path.basename(f).split("_")[1].split(".")[0]), f) for d in (R3, R4) for f in glob.glob(f"{d}/txs_*.jsonl.gz")]
    jobs = collections.defaultdict(lambda: collections.defaultdict(list))
    for sig, e in D.items():
        t = e["t"]
        for c, f in chunks:
            if not (c - 300 <= t <= c + 330): continue
            if f.startswith(R3) and t > R3_END: continue
            if f.startswith(R4) and t < R4_START: continue
            jobs[f][e["m"]].append(e["s"])
    todo = sorted(jobs.items())
    print(f"dumps {len(D)}; chunks to scan {len(todo)}", flush=True)
    t0 = time.time(); tot = 0
    with Pool(nw) as pool:
        for k, (name, n, dt) in enumerate(pool.imap_unordered(work, todo), 1):
            tot += max(n, 0)
            if k % 10 == 0 or k == len(todo): print(f"{k}/{len(todo)} {name} rows {n} {dt:.1f}s  total {tot}  elapsed {time.time() - t0:.0f}s", flush=True)
