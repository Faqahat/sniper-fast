#!/usr/bin/env python3
# freshaudit extraction (read-only on raw collector chunks; writes only into ./x/<run>/)
# per chunk: D = sells >= 0.5 SOL (dumps), F = every tx (ok or failed) on a dumped mint within slots [dump_s, dump_s+3]
# after the dump, O = txs signed by our wallet, plus per-chunk aggregates (relay usage, signer stats, per-slot max index).
# usage: python3 -I extract.py <run_dir> <out_dir> [procs] [first_unix] [last_unix]
import sys, os, json, gzip, base64, glob, zlib, collections
from multiprocessing import Pool
RUN, OUT = sys.argv[1], sys.argv[2]
PROCS = int(sys.argv[3]) if len(sys.argv) > 3 else 4
T0 = int(sys.argv[4]) if len(sys.argv) > 4 else 0
T1 = int(sys.argv[5]) if len(sys.argv) > 5 else 10**12
OURS = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"
TIPMAP = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tipmap.json")))
TRADE = bytes([189, 219, 127, 211, 78, 230, 97, 238])
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
STD = {"11111111111111111111111111111111", "ComputeBudget111111111111111111111111111111", "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
       "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL", "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
       "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ", "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA", "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr",
       "Memo1UhkJRfHyvLMcVucJwxXeuD728EQVDDwQDxFMNo"}
DUMP_MIN = 500_000_000
WIN = 3

def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))

def errcode(e):
    if not e: return None
    try:
        ie = e.get("InstructionError")
        if ie:
            x = ie[1]
            if isinstance(x, dict) and "Custom" in x: return f"{ie[0]}:{x['Custom']}"
            return f"{ie[0]}:{x if isinstance(x, str) else json.dumps(x, separators=(',', ':'))}"
        return json.dumps(e, separators=(",", ":"))[:60]
    except Exception:
        return str(e)[:60]

def parse(line):
    r = json.loads(line)
    evs = []
    for e in r.get("ev") or []:
        try: raw = base64.b64decode(e + "=" * (-len(e) % 4))
        except Exception: continue
        if raw[:8] != TRADE or len(raw) < 225: continue
        u = lambda o: int.from_bytes(raw[o:o + 8], "little")
        evs.append([b58(raw[8:40]), raw[56], u(40), u(48), b58(raw[57:89]), u(97), u(105)])
    tips = [[TIPMAP.get(a, "?" + a[:6]), int(l)] for a, l in (r.get("tips") or [])]
    progs = [p[:8] for p in (r.get("progs") or []) if p not in STD]
    signers = r.get("signers") or []
    return dict(s=r["s"], i=r["i"], bt=r.get("bt"), sig=r["sig"], sg=signers[0] if signers else None, nsg=len(signers),
                fee=r.get("fee"), cup=r.get("cup"), cul=r.get("cul"), cu=r.get("cu"), tips=tips, err=errcode(r.get("err")),
                ixn=r.get("ixn") or [], progs=progs, mints=r.get("mints") or [], ev=evs,
                sd=r.get("sd") if (OURS in signers) else None, signers=signers if len(signers) > 1 else None)

def lines(path, max_bt=None):
    try:
        with gzip.open(path, "rt") as f:
            for line in f:
                yield line
    except (EOFError, OSError, zlib.error):
        return

def work(args):
    path, nxt = args
    tag = os.path.basename(path).split(".")[0]
    outp = os.path.join(OUT, tag + ".jsonl.gz")
    if os.path.exists(outp): return tag, -1
    rows = []
    for line in lines(path):
        try: rows.append(parse(line))
        except Exception: continue
    nmain = len(rows)
    if nxt:                                           # head of the next chunk: the first WIN+2 slots
        s_last = rows[-1]["s"] if rows else 0
        for line in lines(nxt):
            try: r = parse(line)
            except Exception: continue
            if r["s"] > s_last + WIN + 1: break
            r["_head"] = 1; rows.append(r)
    # dumps
    dumps = collections.defaultdict(list)            # mint -> [(s, i)]
    D = []
    for k, r in enumerate(rows[:nmain]):
        if r["err"]: continue
        for j, e in enumerate(r["ev"]):
            if e[1] == 0 and e[2] >= DUMP_MIN:
                dumps[e[0]].append((r["s"], r["i"])); D.append(dict(r, j=j, dm=e[0]))
    F = []; seenF = set()
    for r in rows:
        ms = set(r["mints"]) | {e[0] for e in r["ev"]}
        for m in ms:
            for (ds, di) in dumps.get(m, ()):
                if ds <= r["s"] <= ds + WIN and (r["s"], r["i"]) > (ds, di):
                    if r["sig"] not in seenF:
                        seenF.add(r["sig"]); F.append(r)
                    break
    O = [r for r in rows[:nmain] if r["sg"] == OURS or (r["signers"] and OURS in r["signers"])]
    # aggregates over the main chunk
    slot_max = collections.defaultdict(lambda: [0, 0])
    relay = collections.Counter(); relay_tip = collections.Counter()
    sgn = {}
    for r in rows[:nmain]:
        sm = slot_max[r["s"]]; sm[0] = max(sm[0], r["i"]); sm[1] += 1
        rel = ",".join(sorted({t[0] for t in r["tips"]})) or "-"
        isbuy = any(e[1] == 1 for e in r["ev"]) or any(x.startswith("Buy") for x in r["ixn"])
        key = f"{rel}|{'F' if r['err'] else 'S'}|{'B' if isbuy else 'o'}"
        relay[key] += 1; relay_tip[key] += sum(t[1] for t in r["tips"])
        g = r["sg"]
        if g:
            x = sgn.get(g)
            if x is None: x = sgn[g] = [0, 0, 0, 0, collections.Counter()]   # txs, failed, buys(ok), tips lamports, relays
            x[0] += 1; x[1] += 1 if r["err"] else 0; x[2] += 1 if (not r["err"] and any(e[1] == 1 for e in r["ev"])) else 0
            x[3] += sum(t[1] for t in r["tips"]); x[4][rel] += 1
    with gzip.open(outp + ".tmp", "wt", compresslevel=3) as f:
        for r in D: f.write(json.dumps(["D", r], separators=(",", ":")) + "\n")
        for r in F: f.write(json.dumps(["F", r], separators=(",", ":")) + "\n")
        for r in O: f.write(json.dumps(["O", r], separators=(",", ":")) + "\n")
        f.write(json.dumps(["SLOTS", {str(k): v for k, v in slot_max.items()}], separators=(",", ":")) + "\n")
        f.write(json.dumps(["RELAY", dict(relay), dict(relay_tip)], separators=(",", ":")) + "\n")
        f.write(json.dumps(["SIGNERS", {g: [x[0], x[1], x[2], x[3], dict(x[4])] for g, x in sgn.items() if x[0] >= 3}], separators=(",", ":")) + "\n")
    os.rename(outp + ".tmp", outp)
    return tag, nmain

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    files = sorted(glob.glob(os.path.join(RUN, "txs", "*.jsonl.gz")))
    sel = [k for k, f in enumerate(files) if T0 <= int(os.path.basename(f)[4:14]) <= T1]
    # never process the newest chunk (still being written)
    jobs = [(files[k], files[k + 1] if k + 1 < len(files) else None) for k in sel if k + 1 < len(files)]
    tot = 0
    with Pool(PROCS) as p:
        for k, (tag, n) in enumerate(p.imap_unordered(work, jobs), 1):
            tot += max(n, 0)
            if k % 20 == 0: print(f"{k}/{len(jobs)} chunks, {tot} txs", flush=True)
    print("DONE", len(jobs), tot, flush=True)
