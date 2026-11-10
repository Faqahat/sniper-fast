#!/usr/bin/env python3
"""BOTREG step 2 [MEASURED, read-only on raw recordings]: per completed hour, operator fingerprints of a WATCH set of wallets
(fee payer = first signer) from the raw pump.fun tx recordings -> /home/it/sniper-data/botreg/fprint/<hour>.pkl
  {u64: {"b58": str, "ntx": n, "nok": n, "tok": Counter(token -> txs)}}
Tokens (one per tx unless noted):
  prog:<id>      every program id outside the common set (router / terminal programs)
  cup:<v>        exact CU price          cupm:<v%1000>  CU-price "bot code" (last 3 digits)
  cul:<v>        exact CU limit          fee:<k>        total fee rounded to 1,000 lamports
  tipa:<lamports> tip amount             tip:<acct>     tip account
  aux:<acct>     every other SOL-moving account (counted once per distinct mint per chunk -> curve accounts stay at 1)
  ixs:<names>    instruction-name sequence   bsz:<SOL to 0.01>  buy size from the TradeEvent
  err:<code>     custom error code of a failed tx   nsig:<n> number of signers
The watch set is given as a file of u64 ids (one per line); a wallet's b58 is taken from the signer string itself.
usage: x2_fprint.py WATCH_FILE [--hours H0 H1]   env NW workers (default 4)"""
import sys, os, gzip, json, base64, struct, glob, time, pickle, collections
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

OUT = f"{C.DATA}/fprint"
DISC = bytes.fromhex("bddb7fd34ee661ee")
COMMON = {"11111111111111111111111111111111", "ComputeBudget111111111111111111111111111111",
          "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
          "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL", "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
          "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA", "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ",
          "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr", "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo",
          "ComputeBudget111111111111111111111111111111", "SysvarRent111111111111111111111111111111111"}
WATCH = set()


def scan(fn):
    """one recording chunk -> {u64: [b58, ntx, nok, Counter]}"""
    out = {}; cache = {}; auxm = collections.defaultdict(set)
    try:
        with gzip.open(fn, "rt", errors="replace") as f:
            for l in f:
                k = l.find('"signers":["')
                if k < 0: continue
                e = l.find('"', k + 12); s = l[k + 12:e]
                u = cache.get(s)
                if u is None:
                    try: u = cache[s] = C.pk64(s)
                    except KeyError: u = cache[s] = 0
                if u not in WATCH: continue
                try: d = json.loads(l)
                except Exception: continue
                r = out.get(u)
                if r is None: r = out[u] = [s, 0, 0, collections.Counter()]
                r[1] += 1; c = r[3]
                err = d.get("err")
                if err is None: r[2] += 1
                else:
                    try:
                        ie = err.get("InstructionError") if isinstance(err, dict) else None
                        code = ie[1].get("Custom") if ie and isinstance(ie[1], dict) else None
                        c[f"err:{code if code is not None else str(err)[:24]}"] += 1
                    except Exception: c["err:?"] += 1
                for p in d.get("progs") or []:
                    if p not in COMMON: c["prog:" + p] += 1
                cup, cul, fee = d.get("cup"), d.get("cul"), d.get("fee") or 0
                c[f"cup:{cup}"] += 1
                if cup: c[f"cupm:{cup % 1000}"] += 1
                c[f"cul:{cul}"] += 1; c[f"fee:{int(round(fee / 1000))}"] += 1
                c["ixs:" + "|".join(d.get("ixn") or [])[:80]] += 1
                c[f"nsig:{len(d.get('signers') or [])}"] += 1
                tips = d.get("tips") or []
                ta = set()
                for a, v in tips:
                    c[f"tip:{a}"] += 1; c[f"tipa:{v}"] += 1; ta.add(a)
                if not tips: c["tipa:0"] += 1
                mint = (d.get("mints") or [""])[0]
                for a, v in d.get("sd") or []:
                    if a == s or a in ta: continue
                    auxm[(u, a)].add(mint)
                for ev in d.get("ev") or []:
                    try: raw = base64.b64decode(ev)
                    except Exception: continue
                    if raw[:8] != DISC or len(raw) < 129: continue
                    sol, = struct.unpack_from("<Q", raw, 40)
                    if raw[56] == 1: c[f"bsz:{sol / 1e9:.2f}"] += 1
                    break
    except (EOFError, OSError):
        pass
    for (u, a), ms in auxm.items():
        out[u][3]["aux:" + a] += len(ms)
    return fn, out


def init(wf):
    global WATCH
    WATCH = {int(x) for x in open(wf).read().split()}


def chunks_by_hour():
    """{hour: [gz paths]} for every recording chunk (one copy per chunk start time)"""
    by = collections.defaultdict(list)
    runs = {}
    for fn in glob.glob(f"{C.COLLECT}/run_*/txs/txs_*.jsonl.gz"):
        runs.setdefault(fn.split("/txs/")[0], []).append((int(os.path.basename(fn)[4:-9]), fn))
    rk = sorted(runs, key=lambda r: min(runs[r]))
    for i, r in enumerate(rk):
        nxt = min(runs[rk[i + 1]])[0] if i + 1 < len(rk) else 1 << 40      # overlapping run tails: keep the earlier run only up to the next run's start
        for t, fn in runs[r]:
            if t >= nxt or os.path.getmtime(fn) > time.time() - 240: continue
            by[C.hour_of(t)].append(fn)
    return dict(sorted(by.items()))


def merge(dst, src):
    for u, (s, n, ok, c) in src.items():
        r = dst.get(u)
        if r is None: dst[u] = {"b58": s, "ntx": n, "nok": ok, "tok": collections.Counter(c)}
        else: r["ntx"] += n; r["nok"] += ok; r["tok"].update(c)


def run(watch_file, hours=None, nw=4, tag=""):
    """scan the given hours (default: all complete hours without an output) for the watch set; one pickle per hour.
    tag != '' writes <hour>.<tag>.pkl (backfill for wallets added later)."""
    os.makedirs(OUT, exist_ok=True)
    by = chunks_by_hour()
    hs = [h for h in by if (hours is None or h in hours) and not os.path.exists(f"{OUT}/{h}{'.' + tag if tag else ''}.pkl")]
    files = [(h, fn) for h in hs for fn in by[h]]
    res = collections.defaultdict(dict); left = collections.Counter(h for h, _ in files)
    fh = {fn: h for h, fn in files}
    t0 = time.time()
    with Pool(nw, initializer=init, initargs=(watch_file,)) as p:
        for k, (fn, out) in enumerate(p.imap_unordered(scan, [fn for _, fn in files], chunksize=1)):
            h = fh[fn]; merge(res[h], out); left[h] -= 1
            if left[h] == 0:
                pth = f"{OUT}/{h}{'.' + tag if tag else ''}.pkl"
                pickle.dump(res.pop(h), open(pth + ".tmp", "wb")); os.rename(pth + ".tmp", pth)
            if k % 100 == 0: print(k, len(files), round(time.time() - t0), flush=True)
    return hs


if __name__ == "__main__":
    hrs = None
    if "--hours" in sys.argv:
        i = sys.argv.index("--hours"); h0, h1 = int(sys.argv[i + 1]), int(sys.argv[i + 2])
        hrs = set(range(C.hour_of(h0), h1, C.H))
    tag = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else ""
    done = run(sys.argv[1], hrs, int(os.environ.get("NW", "4")), tag)
    print("done hours", len(done), flush=True)
