#!/usr/bin/env python3
# INSTANT-BOTS study, step 6 (read-only, local recording only): EVERY recorded tx signed by a set of wallets (failed ones, trades,
# AND successful txs without a trade = possible "no-op" conditional attempts that check a price and do nothing), straight from
# the collector's raw chunks, as compact rows -> OUT.jsonl.gz:
#   [s, i, sig, signers, err, fee, cup, cul, cu, progs_ns, ixn, mints, trades(list of [mint, buy, sol, tok, user]), tips([[svc, lamports]]), sd_signer0]
# usage: nice python3 -I i6_wallet_txs.py RUN_DIR WALLETS.json OUT.jsonl.gz [workers]
import sys, os, json, glob, gzip, base64, subprocess, time
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
def init(wf): G["W"] = set(json.load(open(wf)))
def work(path):
    W = G["W"]; out = []
    p = subprocess.Popen(["zcat", path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=1 << 20)
    for l in p.stdout:
        k = l.find(b'"signers":[')
        if k < 0: continue
        e = l.find(b"]", k)
        sg = [x.strip(b'"').decode() for x in l[k + 11:e].split(b",")]
        if not any(x in W for x in sg): continue
        try: r = json.loads(l)
        except Exception: continue
        tr = []
        for s in r.get("ev") or []:
            try: raw = base64.b64decode(s + "=" * (-len(s) % 4))
            except Exception: continue
            if raw[:8] != TD or len(raw) < 113: continue
            u = lambda o: int.from_bytes(raw[o:o + 8], "little")
            tr.append([b58enc(raw[8:40]), raw[56], u(40), u(48), b58enc(raw[57:89])])
        sd = {a: int(v) for a, v in (r.get("sd") or [])}
        out.append([r["s"], r["i"], r["sig"], r["signers"], errc(r.get("err")), r.get("fee"), r.get("cup"), r.get("cul"), r.get("cu"),
                    "|".join(x for x in (r.get("progs") or []) if x not in STD), "|".join((r.get("ixn") or [])[:10]), (r.get("mints") or [])[:3], tr,
                    [[TIP.get(a) or ("nozomi" if a.startswith("noz") else "?" + a[:6]), int(v)] for a, v in (r.get("tips") or [])], sd.get(r["signers"][0], 0)])
    p.wait()
    return path, out
if __name__ == "__main__":
    run, wf, outp = sys.argv[1], sys.argv[2], sys.argv[3]; P = int(sys.argv[4]) if len(sys.argv) > 4 else 4
    now = time.time()
    jobs = [f for f in sorted(glob.glob(f"{run}/txs/*.jsonl.gz")) if now - os.path.getmtime(f) > 180]
    n = 0; k = 0
    with Pool(P, initializer=init, initargs=(wf,)) as pool, gzip.open(outp + ".tmp", "wt", compresslevel=3) as fo:
        for path, out in pool.imap_unordered(work, jobs):
            k += 1; n += len(out)
            for r in out: fo.write(json.dumps(r, separators=(",", ":")) + "\n")
            if k % 20 == 0: print(f"{k}/{len(jobs)} chunks, {n} rows", flush=True)
    os.rename(outp + ".tmp", outp)
    print("DONE", n, flush=True)
