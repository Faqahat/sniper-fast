#!/usr/bin/env python3
# INSTANT-BOTS study, pass 1 (read-only, local recording only). For every raw chunk of a collector run (txs/*.jsonl.gz, FAILED
# txs included) write two compact gz jsonl files to the output dir:
#   T_<chunk>.jsonl.gz  one row per pump TradeEvent of a SUCCESSFUL tx:
#       [s, i, j, sig, signers, user, mint, buy, sol, tok, vsol, vtok, fee, cup, cul, cu, tip_total, tip_svcs, progs_ns, sdw, ixn]
#   F_<chunk>.jsonl.gz  one row per FAILED tx (any program, every tracked mint it touched):
#       [s, i, sig, signers, mints, err, fee, cup, cul, cu, progs_ns, ixn]
# s = slot, i = index in the full block (votes included, the collector's index), j = event index inside the tx,
# progs_ns = programs other than the standard ones (system, compute budget, token, ATA, pump, pump fees, pump AMM),
# err = "<custom code or name>@<instruction index>", tip_svcs = landing services of the tip transfers (collector tip map).
# usage: nice python3 -I i1_extract.py RUN_DIR OUT_DIR [workers]     (skips chunks already done; skips a chunk written < 3 min ago)
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
    try:
        ie = err.get("InstructionError") if isinstance(err, dict) else None
        if ie:
            c = ie[1]
            if isinstance(c, dict): c = c.get("Custom", next(iter(c)))
            return f"{c}@{ie[0]}"
        return next(iter(err)) if isinstance(err, dict) else str(err)
    except Exception: return str(err)[:40]
def svc(a): return TIP.get(a) or ("nozomi" if a.startswith("noz") else "?" + a[:6])
def work(arg):
    path, out = arg
    name = os.path.basename(path).split("_")[1].split(".")[0]
    tp, fp = f"{out}/T_{name}.jsonl.gz", f"{out}/F_{name}.jsonl.gz"
    if os.path.exists(tp) and os.path.exists(fp): return name, -1, -1, 0.0
    t0 = time.time(); nt = nf = 0
    ft = gzip.open(tp + ".tmp", "wt", compresslevel=3); ff = gzip.open(fp + ".tmp", "wt", compresslevel=3)
    p = subprocess.Popen(["zcat", path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=1 << 20)
    for l in p.stdout:
        try: r = json.loads(l)
        except Exception: continue
        sg = r.get("signers") or []
        pns = "|".join(x for x in (r.get("progs") or []) if x not in STD)
        ixn = "|".join((r.get("ixn") or [])[:8])
        if r.get("err"):
            ff.write(json.dumps([r["s"], r["i"], r["sig"], sg, (r.get("mints") or [])[:3], errc(r["err"]), r.get("fee"), r.get("cup"), r.get("cul"), r.get("cu"), pns, ixn],
                                separators=(",", ":")) + "\n"); nf += 1
            continue
        evs = r.get("ev") or []
        if not evs: continue
        tips = r.get("tips") or []
        tt = sum(int(v) for _, v in tips); ts = "|".join(sorted({svc(a) for a, _ in tips}))
        sd = {a: int(v) for a, v in (r.get("sd") or [])}
        sdw = sd.get(sg[0], 0) if sg else 0
        j = 0
        for s in evs:
            try: raw = base64.b64decode(s + "=" * (-len(s) % 4))
            except Exception: continue
            if raw[:8] != TD or len(raw) < 113: continue
            u = lambda o: int.from_bytes(raw[o:o + 8], "little")
            ft.write(json.dumps([r["s"], r["i"], j, r["sig"], sg, b58enc(raw[57:89]), b58enc(raw[8:40]), raw[56], u(40), u(48), u(97), u(105), r.get("fee"), r.get("cup"),
                                 r.get("cul"), r.get("cu"), tt, ts, pns, sdw, ixn], separators=(",", ":")) + "\n")
            j += 1; nt += 1
    p.wait(); ft.close(); ff.close()
    os.rename(tp + ".tmp", tp); os.rename(fp + ".tmp", fp)
    return name, nt, nf, time.time() - t0
if __name__ == "__main__":
    run, out = sys.argv[1], sys.argv[2]; P = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    os.makedirs(out, exist_ok=True)
    now = time.time()
    jobs = [(f, out) for f in sorted(glob.glob(f"{run}/txs/*.jsonl.gz")) if now - os.path.getmtime(f) > 180]
    print(f"{len(jobs)} chunks", flush=True)
    k = 0
    with Pool(P) as pool:
        for name, nt, nf, dt in pool.imap_unordered(work, jobs):
            k += 1
            if nt >= 0: print(f"{k}/{len(jobs)} {name} trades {nt} failed {nf} {dt:.0f}s", flush=True)
    print("DONE", flush=True)
