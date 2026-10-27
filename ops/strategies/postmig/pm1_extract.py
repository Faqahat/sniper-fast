#!/usr/bin/env python3
# POST-MIGRATION STUDY, pass 1 (read-only). One pass over the raw recorder chunks of R2, R3, R4:
#  - PumpSwap (pAMM) Buy/SellEvents of successful txs  -> amm table (one row per event)
#  - failed txs that touch PumpSwap                      -> fail table (compact)
#  - pump.fun bonding-curve TradeEvents                  -> bc table (pre-migration context)
#  - migrations (CreatePoolEvent + CompletePumpAmmMigrationEvent) -> mig list
#  - per slot: max tx index seen (block-size estimate) and block time
# Output: /home/moiz/sniper-data/strategies/postmig/tmp/<RUN>/<chunk>.pkl  (numpy columns + local string table)
# Usage: pm1_extract.py [RUN ...]   (default R2 R3 R4); 3 worker processes.
import sys, os, json, glob, struct, base64, hashlib, pickle, subprocess, time, zlib
from array import array
from multiprocessing import Pool
import numpy as np

COL = "/home/moiz/sniper-data/collect"
OUT = "/home/moiz/sniper-data/strategies/postmig/tmp"
RUNS = {"R1": "run_20261021_2207", "R2": "run_20261022_1543", "R3": "run_20261023_1426", "R4": "run_20261024_1425"}
D = lambda n: hashlib.sha256(("event:" + n).encode()).digest()[:8]
BUY, SELL, CPE, MIG, TRADE = D("BuyEvent"), D("SellEvent"), D("CreatePoolEvent"), D("CompletePumpAmmMigrationEvent"), D("TradeEvent")
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
IXC = {b"buy_exact_quote_in": 1, b"buy": 2, b"buy_exact_quote_in_v2": 3, b"buy_v2": 4, b"multi_hop_swap": 5}
BIG = (1 << 63) - 1
TIPMAP = json.load(open("/home/moiz/sniper/ops/agents/tipmap.json"))

def b58(bs):
    n = int.from_bytes(bs, "big"); s = ""
    while n: n, r = divmod(n, 58); s = B58[r] + s
    return "1" * (len(bs) - len(bs.lstrip(b"\0"))) + s

def dec(e):
    try: return base64.b64decode(e)
    except Exception: return b""

AMM_COLS = ["s", "i", "k", "bt", "side", "pool", "user", "signer", "cc", "base", "qtot", "qcurve", "B", "Q", "lpb", "prb", "ccb",
            "lim", "minbase", "ixc", "fee", "cup", "cul", "cu", "tip", "relay", "nev", "nbc", "sig"]
FAIL_COLS = ["s", "i", "signer", "mint", "err", "fee", "cup", "tip", "relay", "nmints"]
BC_COLS = ["s", "i", "k", "bt", "mint", "user", "signer", "isbuy", "sol", "tok", "vsol", "vtok", "rsol", "fbps", "cup", "tip", "relay", "sig"]

I32 = (1 << 31) - 1
DT = {"s": np.int32, "i": np.int32, "k": np.int8, "bt": np.int32, "side": np.int8, "pool": np.int32, "user": np.int32, "signer": np.int32,
      "cc": np.int32, "mint": np.int32, "lpb": np.int16, "prb": np.int16, "ccb": np.int16, "ixc": np.int8, "fee": np.int32, "cup": np.int32,
      "cul": np.int32, "cu": np.int32, "tip": np.int32, "relay": np.int16, "nev": np.int8, "nbc": np.int8, "sig": np.int32, "err": np.int32,
      "nmints": np.int8, "isbuy": np.int8, "fbps": np.int16}
def cols(dct):
    out = {}
    for c, v in dct.items():
        a = np.frombuffer(v, dtype=np.int64) if len(v) else np.zeros(0, np.int64)
        t = DT.get(c, np.int64)
        if t is np.int32: a = np.minimum(a, I32)
        out[c] = a.astype(t)
    return out

def work(args):
    run, path = args
    od = os.path.join(OUT, run); os.makedirs(od, exist_ok=True)
    of = os.path.join(od, os.path.basename(path).replace(".jsonl.gz", ".pkl"))
    if os.path.exists(of) and os.path.getmtime(of) > os.path.getmtime(path): return run, path, "skip"
    strs = {}; strl = []
    def sid(x):
        v = strs.get(x)
        if v is None: v = strs[x] = len(strl); strl.append(x)
        return v
    amm = {c: array("q") for c in AMM_COLS}; fail = {c: array("q") for c in FAIL_COLS}; bc = {c: array("q") for c in BC_COLS}
    migs = []; slots = {}
    n = 0; bad = 0
    p = subprocess.Popen(["zcat", path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=1 << 20)
    for line in p.stdout:
        n += 1
        # slot / index / block time without a full parse: {"s":..,"i":..,"bt":..
        try:
            a = line.index(b",", 5); s = int(line[5:a]); b_ = line.index(b",", a + 5); i = int(line[a + 5:b_])
            c = line.index(b",", b_ + 6); bt = int(line[b_ + 6:c])
        except ValueError:
            bad += 1; continue
        mx = slots.get(s)
        if mx is None or i > mx[0]: slots[s] = (i, bt)
        has_amm = b"pAMMBay" in line
        ok = b'"err":null' in line
        if not (has_amm or (ok and b"6EF8rrect" in line)): continue
        try: t = json.loads(line)
        except ValueError: bad += 1; continue
        signer = t["signers"][0] if t["signers"] else ""
        tips = t.get("tips") or []
        tip = sum(x[1] for x in tips if isinstance(x, list) and len(x) > 1)
        relay = sid(TIPMAP.get(tips[0][0], "?")) if tips and isinstance(tips[0], list) else -1
        cup = t.get("cup") or 0; fee = t.get("fee") or 0
        if t["err"] is not None:
            if not has_amm: continue
            e = t["err"]; code = -1
            try:
                ie = e.get("InstructionError")
                if ie:
                    cc = ie[1]; code = ie[0] * 100000 + (cc.get("Custom", 99999) if isinstance(cc, dict) else 99998)
            except Exception: pass
            ms = t.get("mints") or []
            for col, v in zip(FAIL_COLS, (s, i, sid(signer), sid(ms[0]) if ms else -1, code, fee, cup, tip, relay, len(ms))): fail[col].append(v)
            continue
        evs = [dec(x) for x in t["ev"]]
        nev = sum(1 for b in evs if b[:8] in (BUY, SELL)); nbc = sum(1 for b in evs if b[:8] == TRADE)
        sg = None
        k = 0
        cpe = None; mg = None
        for b in evs:
            d8 = b[:8]
            if d8 == BUY or d8 == SELL:
                if len(b) < 8 + 14 * 8 + 7 * 32 + 16: continue
                ts, base, lim, ubr, uqr, B, Q, q, lpb, lpf, prb, prf, q2, uq = struct.unpack_from("<q13Q", b, 8)
                o = 8 + 14 * 8
                pool = b58(b[o:o + 32]); user = b58(b[o + 32:o + 64]); cc = b58(b[o + 192:o + 224])
                ccb, ccf = struct.unpack_from("<2Q", b, o + 224)
                if d8 == BUY:
                    side = 1; qtot = q; qcurve = uq; minbase = 0; ixc = 0
                    off = o + 224 + 16 + 1 + 5 * 8
                    if len(b) >= off + 4:
                        L = struct.unpack_from("<I", b, off)[0]; ixn = b[off + 4:off + 4 + L]; ixc = IXC.get(ixn, 9)
                        minbase = struct.unpack_from("<Q", b, off - 8)[0]
                else:
                    side = -1; qtot = uq; qcurve = q; minbase = 0; ixc = 6
                if sg is None: sg = sid(t["sig"])
                row = (s, i, k, bt, side, sid(pool), sid(user), sid(signer), sid(cc), base, qtot, qcurve, B, Q, lpb, prb, ccb, lim, minbase,
                       ixc, fee, cup, t.get("cul") or 0, t.get("cu") or 0, tip, relay, nev, nbc, sg)
                for col, v in zip(AMM_COLS, row): amm[col].append(v if v < BIG else BIG)
                k += 1
            elif d8 == TRADE:
                if len(b) < 225: continue
                mint = b58(b[8:40]); sol, tok = struct.unpack_from("<2Q", b, 40); isb = b[56]; user = b58(b[57:89])
                vsol, vtok, rsol, rtok = struct.unpack_from("<4Q", b, 97)
                fbps = struct.unpack_from("<Q", b, 161)[0]; ccbps = struct.unpack_from("<Q", b, 209)[0]
                if sg is None: sg = sid(t["sig"])
                row = (s, i, k, bt, sid(mint), sid(user), sid(signer), isb, sol, tok, vsol, vtok, rsol, fbps + ccbps, cup, tip, relay, sg)
                for col, v in zip(BC_COLS, row): bc[col].append(v if v < BIG else BIG)
                k += 1
            elif d8 == CPE and len(b) >= 333:
                o = 8; ts, idx = struct.unpack_from("<qH", b, o); o += 10
                cr = b58(b[o:o + 32]); bm = b58(b[o + 32:o + 64]); qm = b58(b[o + 64:o + 96]); o += 96 + 2
                vals = struct.unpack_from("<7Q", b, o); o += 56 + 1
                pk = [b58(b[o + 32 * j:o + 32 * j + 32]) for j in range(5)]; o += 160
                cpe = dict(creator=cr, base_mint=bm, quote_mint=qm, base_in=vals[0], quote_in=vals[1], pool_base=vals[2], pool_quote=vals[3],
                           pool=pk[0], lp_mint=pk[1], coin_creator=pk[4], tail=b[o:].hex())
            elif d8 == MIG and len(b) >= 168:
                o = 8; u = b58(b[o:o + 32]); m = b58(b[o + 32:o + 64]); ma, sa, mf = struct.unpack_from("<3Q", b, o + 64)
                pool = b58(b[o + 128:o + 160])
                mg = dict(user=u, mint=m, mint_amount=ma, sol_amount=sa, mig_fee=mf, pool=pool)
        if cpe is not None or mg is not None:
            migs.append(dict(s=s, i=i, bt=bt, sig=t["sig"], signers=t["signers"], mints=t.get("mints"), ixn=t.get("ixn"), cpe=cpe, mig=mg,
                             nev=nev, nbc=nbc, sd=t.get("sd")[:12], tb=t.get("tb"), fee=fee, cup=cup, tip=tip))
    p.wait()
    res = dict(run=run, chunk=os.path.basename(path), n=n, bad=bad, strl=strl, migs=migs, slots=slots,
               amm=cols(amm), fail=cols(fail), bc=cols(bc))
    tmp = of + ".tmp"
    with open(tmp, "wb") as f: f.write(zlib.compress(pickle.dumps(res, protocol=5), 1))
    os.replace(tmp, of)
    return run, path, f"n={n} amm={len(amm['s'])} bc={len(bc['s'])} fail={len(fail['s'])} migs={len(migs)} bad={bad}"

if __name__ == "__main__":
    runs = sys.argv[1:] or ["R2", "R3", "R4"]
    jobs = []
    for r in runs:
        fs = sorted(glob.glob(os.path.join(COL, RUNS[r], "txs", "*.jsonl.gz")))
        jobs += [(r, f) for f in fs]
    t0 = time.time(); done = 0
    with Pool(3) as pool:
        for run, path, msg in pool.imap_unordered(work, jobs, chunksize=1):
            done += 1
            if done % 20 == 0 or done == len(jobs):
                print(f"{done}/{len(jobs)} {time.time()-t0:.0f}s {run} {os.path.basename(path)} {msg}", flush=True)

def load_chunk(path):
    with open(path, "rb") as f: return pickle.loads(zlib.decompress(f.read()))
