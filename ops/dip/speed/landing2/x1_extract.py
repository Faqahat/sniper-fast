#!/usr/bin/env python3
# HOW PROS LAND, pass 1 (read-only, local recording only). One raw collector chunk -> compact files in OUT:
#   T_<chunk>.jsonl.gz  one row per pump TradeEvent of a SUCCESSFUL tx (all wallets):
#       [s, i, sig, signer0, user, mint, buy, sol, vsol, vtok, fee, cup, cul, cu, tip_total, tip_svcs, nsig]
#   W_<chunk>.jsonl.gz  every tx (failed too) signed by a target wallet (wallets.json): full detail incl. positive SOL deltas
#   B_<chunk>.json      per slot: [max index seen, txs seen, first bt]
#   R_<chunk>.json      positive-SOL-delta recipients of small amounts (<= 0.05 SOL) across all successful txs:
#                       addr -> [n txs, n distinct signers, total lamports]   (to find tip accounts we do not know yet)
# usage: nice python3 -I x1_extract.py RUN_DIR OUT_DIR [workers]
import sys, os, json, glob, gzip, base64, subprocess, time, collections
from multiprocessing import Pool
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238])
TIP = json.load(open("/home/moiz/sniper/ops/dip/speed/night/tipmap.json"))
WAL = json.load(open("/home/moiz/sniper-data/landing2/wallets.json"))
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58enc(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
def svc(a): return TIP.get(a) or ("nozomi" if a.startswith("noz") else "?" + a[:8])
def work(arg):
    path, out = arg
    name = os.path.basename(path).split("_")[1].split(".")[0]
    tp, wp, bp, rp = f"{out}/T_{name}.jsonl.gz", f"{out}/W_{name}.jsonl.gz", f"{out}/B_{name}.json", f"{out}/R_{name}.json"
    if all(os.path.exists(x) for x in (tp, wp, bp, rp)): return name, -1, -1, 0.0
    t0 = time.time(); nt = nw = 0
    ft = gzip.open(tp + ".tmp", "wt", compresslevel=3); fw = gzip.open(wp + ".tmp", "wt", compresslevel=3)
    blk = {}; rec = collections.defaultdict(lambda: [0, set(), 0])
    p = subprocess.Popen(["zcat", path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=1 << 20)
    for l in p.stdout:
        try: r = json.loads(l)
        except Exception: continue
        s = r.get("s"); i = r.get("i")
        if s is None or i is None: continue
        b = blk.get(s)
        if b is None: blk[s] = [i, 1, r.get("bt")]
        else:
            b[1] += 1
            if i > b[0]: b[0] = i
        sg = r.get("signers") or []
        s0 = sg[0] if sg else ""
        sd = r.get("sd") or []
        if any(x in WAL for x in sg):
            fw.write(json.dumps([s, i, r["sig"], sg, r.get("err"), r.get("fee"), r.get("cup"), r.get("cul"), r.get("cu"), (r.get("mints") or [])[:3],
                                 r.get("progs") or [], (r.get("ixn") or [])[:12], r.get("tips") or [], [x for x in sd if x[1] > 0 and x[0] not in sg]],
                                separators=(",", ":")) + "\n"); nw += 1
        if r.get("err"): continue
        for a, v in sd:
            if 0 < v <= 50_000_000 and a not in sg:
                x = rec[a]; x[0] += 1; x[1].add(s0); x[2] += v
        evs = r.get("ev") or []
        if not evs: continue
        tips = r.get("tips") or []
        tt = sum(int(v) for _, v in tips); ts = "|".join(sorted({svc(a) for a, _ in tips}))
        for e in evs:
            try: raw = base64.b64decode(e + "=" * (-len(e) % 4))
            except Exception: continue
            if raw[:8] != TD or len(raw) < 113: continue
            u = lambda o: int.from_bytes(raw[o:o + 8], "little")
            ft.write(json.dumps([s, i, r["sig"], s0, b58enc(raw[57:89]), b58enc(raw[8:40]), raw[56], u(40), u(97), u(105), r.get("fee"), r.get("cup"),
                                 r.get("cul"), r.get("cu"), tt, ts, len(sg)], separators=(",", ":")) + "\n")
            nt += 1
    p.wait(); ft.close(); fw.close()
    json.dump(blk, open(bp + ".tmp", "w"))
    json.dump({a: [x[0], len(x[1]), x[2]] for a, x in rec.items() if len(x[1]) >= 5}, open(rp + ".tmp", "w"))
    for x in (tp, wp, bp, rp): os.rename(x + ".tmp", x)
    return name, nt, nw, time.time() - t0
if __name__ == "__main__":
    run, out = sys.argv[1], sys.argv[2]; P = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    os.makedirs(out, exist_ok=True)
    now = time.time()
    jobs = [(f, out) for f in sorted(glob.glob(f"{run}/txs/*.jsonl.gz")) if now - os.path.getmtime(f) > 180]
    if len(sys.argv) > 4: jobs = jobs[:int(sys.argv[4])]
    print(f"{len(jobs)} chunks", flush=True)
    k = 0
    with Pool(P) as pool:
        for name, nt, nw, dt in pool.imap_unordered(work, jobs):
            k += 1
            if nt >= 0: print(f"{k}/{len(jobs)} {name} trades {nt} wallet-txs {nw} {dt:.0f}s", flush=True)
    print("DONE", flush=True)
