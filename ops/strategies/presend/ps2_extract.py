#!/usr/bin/env python3
# Step 1b (read-only): every tx (FAILED ones included) signed by the candidate pre-placer wallets, from the collector's raw
# chunks of R1..R4 (run_*/txs/*.jsonl.gz), plus a per-signer census of failed vs ok pump txs for ALL signers (to find more
# pre-placers: many cheap failed buys + fast fills).
# usage: python3 -I ps2_extract.py <cand_uids.json> [workers]
# -> presend/raw/<day>_<chunk>.jsonl.gz (rows of candidate wallets) + presend/raw/<day>_<chunk>.census.json
import sys, os, json, glob, gzip, base64, subprocess, zlib, collections, time, re
from multiprocessing import Pool
D = "/home/moiz/sniper-data/collect"; OUT = os.environ.get("PS2_OUT", "/home/moiz/sniper-data/strategies/presend/raw")
RUNS = {"R1": "run_20261021_2207", "R2": "run_20261022_1543", "R3": "run_20261023_1426", "R4": "run_20261024_1425"}
PUMP = b"6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
TRADE_DISC = bytes([189, 219, 127, 211, 78, 230, 97, 238])
STD = {"11111111111111111111111111111111", "ComputeBudget111111111111111111111111111111", "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
       "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL", "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
       "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ", "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"}
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
RE_ERR = re.compile(rb'"err":(null|\{"InstructionError":\[(\d+),\{"Custom":(\d+)\}\]\}|\{[^,]*)')
G = {}
def b58enc(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))

def errc(err):
    if not err: return None
    try:
        ie = err.get("InstructionError")
        if ie:
            c = ie[1]
            if isinstance(c, dict): c = c.get("Custom", next(iter(c)))
            return f"{c}@{ie[0]}"
        return next(iter(err)) if isinstance(err, dict) else str(err)
    except Exception: return str(err)[:40]

def compact(r):
    tr = []
    for s in r.get("ev") or []:
        try: raw = base64.b64decode(s + "=" * (-len(s) % 4))
        except Exception: continue
        if raw[:8] != TRADE_DISC or len(raw) < 113: continue
        u = lambda o: int.from_bytes(raw[o:o + 8], "little")
        tr.append([b58enc(raw[8:40]), u(40), u(48), raw[56], b58enc(raw[57:89]), u(97), u(105)])
    sg = r.get("signers") or ["?"]
    sd = {a: int(v) for a, v in (r.get("sd") or [])}
    return dict(s=int(r["s"]), i=int(r["i"]), bt=r.get("bt"), sig=r["sig"], w=sg[0], err=errc(r.get("err")), fee=r.get("fee"), cu=r.get("cu"),
                cup=r.get("cup"), cul=r.get("cul"), tips=sum(int(v) for _, v in (r.get("tips") or [])), ntip=len(r.get("tips") or []),
                own=[p for p in (r.get("progs") or []) if p not in STD], ixn=(r.get("ixn") or [])[:10], mints=(r.get("mints") or [])[:3], tr=tr,
                sdw=sd.get(sg[0], 0))

def work(arg):
    day, path = arg
    name = f"{day}_{os.path.basename(path).split('_')[1].split('.')[0]}"
    outp = f"{OUT}/{name}.jsonl.gz"
    if os.path.exists(outp) and os.path.exists(f"{OUT}/{name}.census.json"): return name, -1, 0.0
    t0 = time.time(); CU = G["cand"]
    rows = []; cen = collections.defaultdict(lambda: [0, 0, 0, 0])      # signer -> [pump ok, pump failed, failed 6042/6001, ok buys]
    p = subprocess.Popen(["zcat", path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=1 << 20)
    for l in p.stdout:
        j = l.find(b'"signers":["')
        if j < 0: continue
        k = l.find(b'"', j + 12); w = l[j + 12:k]
        if PUMP not in l: continue
        m = RE_ERR.search(l)
        c = cen[w]
        if m is None or m.group(1) == b"null":
            c[0] += 1
            if b'"Buy' in l: c[3] += 1
        else:
            c[1] += 1
            if m.group(3) in (b"6042", b"6001", b"6002", b"6003"): c[2] += 1
        if zlib.crc32(w) in CU:
            try: rows.append(compact(json.loads(l)))
            except Exception: pass
    p.wait()
    with gzip.open(outp + ".tmp", "wt", compresslevel=3) as f:
        for r in rows: f.write(json.dumps(r, separators=(",", ":")) + "\n")
    os.rename(outp + ".tmp", outp)
    keep = {w.decode(): v for w, v in cen.items() if v[1] >= 5}
    json.dump(keep, open(f"{OUT}/{name}.census.json", "w"))
    return name, len(rows), time.time() - t0

def init(cand): G["cand"] = cand

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    cand = set(json.load(open(sys.argv[1])))
    nw = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    jobs = [(day, f) for day, r in RUNS.items() for f in sorted(glob.glob(f"{D}/{r}/txs/txs_*.jsonl.gz"))]
    print(f"chunks {len(jobs)}, candidate uids {len(cand)}", flush=True)
    t0 = time.time(); tot = 0
    with Pool(nw, initializer=init, initargs=(cand,)) as pool:
        for k, (name, n, dt) in enumerate(pool.imap_unordered(work, jobs), 1):
            tot += max(n, 0)
            if k % 20 == 0 or k == len(jobs): print(f"{k}/{len(jobs)} {name} rows {n} {dt:.1f}s total {tot} elapsed {time.time() - t0:.0f}s", flush=True)
    print("DONE", tot, flush=True)
