#!/usr/bin/env python3
"""QUIET2 step 1 (read-only on the local raw recording copies): a compact chain table of every successful pump.fun trade
(TradeEvent, chain order) with block time in [LO, HI), plus our two wallets' failed txs. Output one npz + ids.json in
/home/moiz/sniper-data/presend_filter/quiet2/. Parsing copied from ops/strategies/presend/flat/f1_extract.py (MEASURED decoder)."""
import sys, os, re, gzip, json, glob, base64, struct, time, collections
import numpy as np
from multiprocessing import Pool

REC = "/home/moiz/sniper-data/collect"
OUT = "/home/moiz/sniper-data/presend_filter/quiet2"
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
DISC = bytes.fromhex("bddb7fd34ee661ee"); CPI = bytes.fromhex("e445a52e51cb9a1d")
HEAD = re.compile(r'\{"s":\s*(\d+),\s*"i":\s*(\d+),\s*"bt":\s*(\d+)')
A58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
LO, HI = int(sys.argv[1]), int(sys.argv[2])
PROCS = int(sys.argv[3]) if len(sys.argv) > 3 else 7


def b58(b):
    n = int.from_bytes(b, "big"); s = []
    while n:
        n, r = divmod(n, 58); s.append(A58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(s))


def errc(err):
    try:
        ie = err.get("InstructionError") if isinstance(err, dict) else None
        if ie:
            c = ie[1]
            if isinstance(c, dict): c = c.get("Custom", next(iter(c)))
            return f"{c}@{ie[0]}"
        return next(iter(err)) if isinstance(err, dict) else str(err)
    except Exception:
        return str(err)[:40]


def one(fn):
    T = collections.defaultdict(list); F = []; blk = {}; trunc = None; mints = {}; users = {}
    try:
        with gzip.open(fn, "rt") as f:
            for line in f:
                m = HEAD.match(line)
                if not m: continue
                s, i, bt = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if bt < LO or bt >= HI: continue
                b = blk.get(s)
                if b is None or i > b[0]: blk[s] = (i, bt)
                ok = '"err":null' in line
                if ok and '"ev":[]' in line: continue
                if not ok:
                    if not any(w in line for w in OURS): continue
                    try: r = json.loads(line)
                    except Exception: continue
                    sg = (r.get("signers") or ["?"])[0]
                    if sg in OURS: F.append((r["sig"], s, i, r.get("fee") or 0, errc(r.get("err")), sg, (r.get("mints") or [""])[0]))
                    continue
                try: r = json.loads(line)
                except Exception: continue
                evs = r.get("ev")
                if isinstance(evs, str):
                    try: evs = json.loads(evs)
                    except Exception: evs = []
                j = 0
                for e in evs or []:
                    for ch in e.split(" "):
                        try: bb = base64.b64decode(ch + "=" * (-len(ch) % 4))
                        except Exception: continue
                        if bb[:8] == CPI: bb = bb[8:]
                        if bb[:8] != DISC or len(bb) < 225: continue
                        o = 8
                        mint = b58(bb[o:o + 32]); o += 32
                        sol, tok = struct.unpack_from("<QQ", bb, o); o += 16
                        buy = bb[o]; o += 1
                        user = b58(bb[o:o + 32]); o += 32 + 8
                        vsol, vtok = struct.unpack_from("<QQ", bb, o)
                        T["s"].append(s); T["i"].append(i); T["j"].append(j); T["bt"].append(bt); T["buy"].append(buy)
                        T["sol"].append(sol); T["tok"].append(tok); T["vsol"].append(vsol); T["vtok"].append(vtok)
                        T["mint"].append(mints.setdefault(mint, len(mints))); T["user"].append(users.setdefault(user, len(users)))
                        j += 1
    except (EOFError, OSError) as ex:
        trunc = repr(ex)[:80]
    num = {}
    for k, dt in (("s", "u8"), ("i", "u4"), ("j", "u1"), ("bt", "u4"), ("buy", "u1"), ("sol", "u8"), ("tok", "u8"), ("vsol", "u8"), ("vtok", "u8"),
                  ("mint", "u4"), ("user", "u4")):
        num[k] = np.array(T.get(k, []), dtype=dt)
    ml = [None] * len(mints)
    for k, v in mints.items(): ml[v] = k
    ul = [None] * len(users)
    for k, v in users.items(): ul[v] = k
    bs = np.array(sorted((s, v[0], v[1]) for s, v in blk.items()), dtype=np.int64).reshape(-1, 3)
    return fn, num, ml, ul, F, bs, trunc


def main():
    files = []
    for run in sorted(glob.glob(f"{REC}/run_*")):
        for f in sorted(glob.glob(f"{run}/txs/txs_*.jsonl.gz")):
            ts = int(os.path.basename(f)[4:14])
            if ts >= HI or ts < LO - 400: continue
            if time.time() - os.path.getmtime(f) < 120: continue
            files.append(f)
    print(f"{len(files)} chunks, span {LO}..{HI}", flush=True)
    t0 = time.time()
    M = {}; U = {}; parts = []; fails = []; blocks = []; n = 0
    with Pool(PROCS) as p:
        for k, (fn, num, ml, ul, F, bs, trunc) in enumerate(p.imap_unordered(one, files, chunksize=1)):
            mi = np.array([M.setdefault(x, len(M)) for x in ml], dtype=np.uint32)
            ui = np.array([U.setdefault(x, len(U)) for x in ul], dtype=np.uint32)
            if len(num["s"]):
                num["mint"] = mi[num["mint"]]; num["user"] = ui[num["user"]]
            parts.append(num); fails += F; blocks.append(bs); n += len(num["s"])
            if trunc: print("TRUNC", fn, trunc, flush=True)
            if k % 20 == 0: print(f"{k}/{len(files)} {time.time()-t0:.0f}s rows {n} mints {len(M)} users {len(U)}", flush=True)
    cols = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    order = np.lexsort((cols["j"], cols["i"], cols["s"]))
    cols = {k: v[order] for k, v in cols.items()}
    B = np.concatenate(blocks); B = B[np.argsort(B[:, 0])]
    # per slot: max tx index, block time (dedup: keep max)
    bl = {}
    for s, i, bt in B.tolist():
        if s not in bl or i > bl[s][0]: bl[s] = (i, bt)
    B = np.array(sorted((s, v[0], v[1]) for s, v in bl.items()), dtype=np.int64)
    np.savez(f"{OUT}/chain.npz", blocks=B, **cols)
    ml = [None] * len(M)
    for k, v in M.items(): ml[v] = k
    ul = [None] * len(U)
    for k, v in U.items(): ul[v] = k
    json.dump({"mint": ml, "user": ul, "lo": LO, "hi": HI, "files": len(files)}, open(f"{OUT}/ids.json", "w"))
    json.dump(fails, open(f"{OUT}/ourfails.json", "w"))
    print(f"done {time.time()-t0:.0f}s rows {len(cols['s'])} mints {len(M)} users {len(U)} ourfails {len(fails)} blocks {len(B)}", flush=True)


if __name__ == "__main__":
    main()
