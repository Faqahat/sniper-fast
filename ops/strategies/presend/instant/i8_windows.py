#!/usr/bin/env python3
# INSTANT-BOTS study, step 8 (read-only, local recording only): for every fast-follow event (i5), ALL recorded txs (failed, trades,
# successful no-trade txs) that touch the event's mint in the slots [dump slot - 3, dump slot + 1], from the raw chunks -> compact
# rows grouped per (mint, dump slot):  OUT.jsonl.gz rows = [mint, s, i, sig, signers, err, fee, cup, cul, cu, progs_ns, ixn,
# trades([[buy, sol, user]]), tips([[svc, lamports]])]
# usage: nice python3 -I i8_windows.py RUN_DIR FOLLOWERS.json OUT.jsonl.gz [workers] [max_gap]
import sys, os, json, glob, gzip, base64, subprocess, time, collections
from multiprocessing import Pool
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238])
STD = {"11111111111111111111111111111111", "ComputeBudget111111111111111111111111111111", "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
       "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL", "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
       "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ", "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"}
TIP = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58enc(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
def errc(err):
    if not err: return None
    ie = err.get("InstructionError") if isinstance(err, dict) else None
    if ie:
        c = ie[1]
        if isinstance(c, dict): c = c.get("Custom", next(iter(c)))
        return f"{c}@{ie[0]}"
    return next(iter(err)) if isinstance(err, dict) else str(err)
G = {}
def init(fp):
    G["slot"] = collections.defaultdict(set)              # slot -> mints whose window covers it
    for k in json.load(open(fp)):
        m, s = k
        for x in range(s - 3, s + 2): G["slot"][x].add(m)
def work(path):
    SL = G["slot"]; out = []
    p = subprocess.Popen(["zcat", path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=1 << 20)
    for l in p.stdout:
        if l[:5] != b'{"s":': continue
        e = l.find(b",", 5)
        try: s = int(l[5:e])
        except Exception: continue
        ms = SL.get(s)
        if not ms: continue
        k = l.find(b'"mints":[')
        if k < 0: continue
        e2 = l.find(b"]", k)
        mints = [x.strip(b'"').decode() for x in l[k + 9:e2].split(b",")]
        hit = [m for m in mints if m in ms]
        if not hit: continue
        try: r = json.loads(l)
        except Exception: continue
        tr = []
        for x in r.get("ev") or []:
            try: raw = base64.b64decode(x + "=" * (-len(x) % 4))
            except Exception: continue
            if raw[:8] != TD or len(raw) < 113: continue
            tr.append([b58enc(raw[8:40]), raw[56], int.from_bytes(raw[40:48], "little"), b58enc(raw[57:89])])
        for m in hit:
            out.append([m, r["s"], r["i"], r["sig"], r["signers"], errc(r.get("err")), r.get("fee"), r.get("cup"), r.get("cul"), r.get("cu"),
                        "|".join(x for x in (r.get("progs") or []) if x not in STD), "|".join((r.get("ixn") or [])[:10]),
                        [[t[1], t[2], t[3]] for t in tr if t[0] == m], [[TIP.get(a) or ("nozomi" if a.startswith("noz") else "?" + a[:6]), int(v)] for a, v in (r.get("tips") or [])]])
    p.wait()
    return path, out
if __name__ == "__main__":
    run, folp, outp = sys.argv[1], sys.argv[2], sys.argv[3]; P = int(sys.argv[4]) if len(sys.argv) > 4 else 4
    MAXG = int(sys.argv[5]) if len(sys.argv) > 5 else 40
    F = json.load(open(folp))
    keys = sorted({(e["mint"], e["s"]) for e in F["ev"] if e["gap"] <= MAXG})
    kf = outp + ".keys.json"; json.dump(keys, open(kf, "w"))
    print(f"{len(keys)} (mint, slot) windows", flush=True)
    now = time.time()
    jobs = [f for f in sorted(glob.glob(f"{run}/txs/*.jsonl.gz")) if now - os.path.getmtime(f) > 180]
    n = 0; k = 0
    with Pool(P, initializer=init, initargs=(kf,)) as pool, gzip.open(outp + ".tmp", "wt", compresslevel=3) as fo:
        for path, out in pool.imap_unordered(work, jobs):
            k += 1; n += len(out)
            for r in out: fo.write(json.dumps(r, separators=(",", ":")) + "\n")
            if k % 20 == 0: print(f"{k}/{len(jobs)} chunks, {n} rows", flush=True)
    os.rename(outp + ".tmp", outp)
    print("DONE", n, flush=True)
