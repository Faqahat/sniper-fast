#!/usr/bin/env python3
# haqq SELL study, pass 2 (read-only, local recording only): full trade tapes (every pump TradeEvent, chain order) + failed txs
# for every mint haqqiUUX traded (htx_R*.jsonl.gz) and every mint our live runs fired on (our_mints.json). Also per-slot max
# block index seen (intra-slot timing proxy). Output: /home/moiz/sniper-data/haqq/tape/b{00..63}_{run}.jsonl.gz + slotmax_{run}.json
# Workers write their own per-bucket files (b{bb}_{run}_p{pid}.jsonl.gz); readers glob b{bb}_*.
# usage: nice python3 -I h2_tapes.py [procs]
import sys, os, json, gzip, glob, zlib, base64
from multiprocessing import Pool
D = "/home/moiz/sniper-data/collect"; OUT = "/home/moiz/sniper-data/haqq"
RUNS = {"R1": "run_20261021_2207", "R2": "run_20261022_1543", "R3": "run_20261023_1426", "R4": "run_20261024_1425"}
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238])
STD = {"11111111111111111111111111111111", "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P", "ComputeBudget111111111111111111111111111111",
       "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
       "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ", "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr", "Memo1UhkJRfHyvLMcVucJwxXeuD85EtBHgaJ8w9AdoN"}
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
NB = 64
def bk(m): return zlib.crc32(m.encode()) % NB
MS = None
def init(ms):
    global MS; MS = ms
def work(a):
    tag, path = a; rows = []; smax = {}
    try:
        for line in gzip.open(path, "rt"):
            # slot / index are the first two fields: {"s":123,"i":45,...
            try:
                c1 = line.index(","); s = int(line[5:c1]); c2 = line.index(",", c1 + 1); i = int(line[c1 + 5:c2])
                if smax.get(s, -1) < i: smax[s] = i
            except ValueError: pass
            k = line.find('"mints":[')
            if k < 0: continue
            e = line.find("]", k)
            ms = [x.strip('"') for x in line[k + 9:e].split(",") if x]
            hit = [m for m in ms if m in MS]
            if not hit: continue
            r = json.loads(line)
            payer = (r.get("signers") or [None])[0]
            tips = sum(d for _, d in r.get("tips") or [])
            rp = [p for p in r.get("progs") or [] if p not in STD]
            router = rp[0][:8] if rp else ""
            base = [r["s"], r["i"], r.get("bt") or 0, r["sig"], payer, r.get("fee") or 0, r.get("cup") or 0, r.get("cul") or 0, r.get("cu") or 0, tips, router]
            if r.get("err"):
                ec = json.dumps(r["err"], separators=(",", ":"))[:60]
                ixs = " ".join(r.get("ixn") or [])[:80]
                for m in hit: rows.append((bk(m), ["F", m] + base + [ec, ixs]))
                continue
            j = 0
            for ev in r.get("ev") or []:
                try: raw = base64.b64decode(ev + "=" * (-len(ev) % 4))
                except Exception: continue
                if raw[:8] != TD or len(raw) < 225: continue
                m = b58(raw[8:40])
                if m not in MS: j += 1; continue
                u = lambda o: int.from_bytes(raw[o:o + 8], "little")
                rows.append((bk(m), ["T", m] + base + [j, b58(raw[57:89]), raw[56], u(40), u(48), u(97), u(105), u(169), u(217), u(161), u(209)]))
                j += 1
            if j == 0:
                ixs = " ".join(r.get("ixn") or [])[:80]
                for m in hit:
                    tb = [x for x in r.get("tb") or [] if x[0] == m]
                    rows.append((bk(m), ["X", m] + base + [ixs, tb[:6]]))
    except (EOFError, OSError, zlib.error): pass
    # each worker appends to its own per-bucket files (one gzip member per chunk); the parent only collects counts
    byb = {}
    for b, row in rows: byb.setdefault(b, []).append(row)
    for b, rr in byb.items():
        with gzip.open(f"{OUT}/tape/b{b:02d}_{tag}_p{os.getpid()}.jsonl.gz", "at", compresslevel=3) as f:
            f.write("".join(json.dumps(x, separators=(",", ":")) + "\n" for x in rr))
    return tag, len(rows), smax
if __name__ == "__main__":
    P = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    ms = set()
    for t in RUNS:
        for l in gzip.open(f"{OUT}/htx_{t}.jsonl.gz", "rt"):
            ms.update(json.loads(l).get("mints") or [])
    ms |= set(json.load(open(f"{OUT}/our_mints.json")))
    print("mints", len(ms), flush=True)
    os.makedirs(f"{OUT}/tape", exist_ok=True)
    jobs = [(t, f) for t, r in RUNS.items() for f in sorted(glob.glob(f"{D}/{r}/txs/*.jsonl.gz"))]
    SM = {t: {} for t in RUNS}; k = 0; nr = 0
    with Pool(P, initializer=init, initargs=(ms,)) as p:
        for tag, n, smax in p.imap_unordered(work, jobs, chunksize=1):
            k += 1; nr += n
            sm = SM[tag]
            for s, i in smax.items():
                if sm.get(s, -1) < i: sm[s] = i
            if k % 50 == 0: print(f"{k}/{len(jobs)} chunks, {nr} rows", flush=True)
    for t in RUNS: json.dump(SM[t], open(f"{OUT}/slotmax_{t}.json", "w"))
    print("DONE", nr, flush=True)
