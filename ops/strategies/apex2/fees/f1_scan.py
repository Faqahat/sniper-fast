#!/usr/bin/env python3
"""APEX-FEES step 1 (read-only on the raw collect tape): every tx (landed OR failed) that touches a launch's mint in the
create slot cs or cs+1. One row per (tx, mint).
Row: run mint cs ci s i sig err fee cu cup cul nsig signer user buy sol tok ixk tips[[acct,lam]] cre(bool: the create tx)
     xp (non-standard programs, i.e. routers / bot programs)  nb_ixn (ixn names that are not pump/token boilerplate)
usage: f1_scan.py OUTDIR RUNDIR [RUNDIR ...] [--procs 3]"""
import sys, os, gzip, json, base64, glob, re, struct
from multiprocessing import Pool

DISC = bytes.fromhex("bddb7fd34ee661ee"); CPI = bytes.fromhex("e445a52e51cb9a1d"); B64KEY = "vdt/007mY"
HEAD = re.compile(r'\{"s":(\d+),"i":(\d+),"bt":(\d+)')
A58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
STD = {"11111111111111111111111111111111", "ComputeBudget111111111111111111111111111111", "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
       "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL", "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
       "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ", "MAyhSmzXzV1pTf7LsNkrNwkWKTo4ougAJ1PPg47MD4e", "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"}
BOIL = {"TransferChecked", "GetFeesWithQuoteMint", "InitializeAccount3", "GetAccountDataSize", "InitializeImmutableOwner", "CloseAccount",
        "InitializeMint2", "MintTo", "SetAuthority", "Transfer", "SyncNative", "CreateIdempotent", "Create"}
G = {}

def b58(b):
    n = int.from_bytes(b, "big"); s = ""
    while n:
        n, r = divmod(n, 58); s = A58[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s

def trades_for(ev, mint):
    out = []
    for e in ev or []:
        for ch in e.split(" "):
            try: b = base64.b64decode(ch + "=" * (-len(ch) % 4))
            except Exception: continue
            if b[:8] == CPI: b = b[8:]
            if b[:8] != DISC or len(b) < 225: continue
            if b58(b[8:40]) != mint: continue
            sol, tok = struct.unpack_from("<QQ", b, 40); buy = b[56]; user = b58(b[57:89])
            out.append((user, buy, sol, tok))
    return out

def ixkind(ixn):
    k = 0
    for x in ixn:
        if x == "Buy": k |= 1
        elif x == "BuyV3" or x == "BuyV2": k |= 2
        elif x.startswith("BuyExact"): k |= 4
        elif x.startswith("Sell"): k |= 8
        elif x in ("Create", "CreateV2"): k |= 16
    return k

def one(args):
    fn, outdir, run = args
    out = os.path.join(outdir, run, os.path.basename(fn).replace(".jsonl.gz", ".jsonl.gz"))
    if os.path.exists(out): return out, "cached"
    bys = G["bys"][run]; ci = G["ci"][run]
    rows = []; nl = 0; trunc = False
    try:
        with gzip.open(fn, "rt") as f:
            for line in f:
                m = HEAD.match(line)
                if not m: continue
                nl += 1
                s = int(m.group(1))
                cand = bys.get(s)
                if cand is None: continue
                r = json.loads(line)
                ms = [x for x in (r.get("mints") or []) if x in cand]
                if not ms: continue
                i = int(m.group(2)); sg = r.get("signers") or ["?"]; ixn = r.get("ixn") or []
                err = r.get("err")
                xp = [p for p in (r.get("progs") or []) if p not in STD]
                nb = [x for x in ixn if x not in BOIL][:8]
                for mint in ms:
                    cs, cix = ci[mint]
                    tr = trades_for(r.get("ev"), mint) if err is None else []
                    bsol = sum(t[2] for t in tr if t[1]); btok = sum(t[3] for t in tr if t[1])
                    ssol = sum(t[2] for t in tr if not t[1])
                    user = tr[0][0] if tr else sg[0]
                    rows.append(dict(mint=mint, cs=cs, ci=cix, s=s, i=i, sig=r["sig"], err=(json.dumps(err)[:90] if err is not None else None),
                                     fee=r.get("fee"), cu=r.get("cu"), cup=r.get("cup"), cul=r.get("cul"), nsig=len(sg), signer=sg[0],
                                     user=user, ntr=len(tr), buy=int(bsol > 0), sol=bsol, tok=btok, ssol=ssol, ixk=ixkind(ixn),
                                     tips=r.get("tips") or [], cre=int(s == cs and i == cix), xp=xp[:6], nb=nb, bt=int(m.group(3))))
    except (EOFError, OSError, ValueError) as ex:
        trunc = repr(ex)[:80]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".tmp"
    with gzip.open(tmp, "wt") as g:
        for x in rows: g.write(json.dumps(x, separators=(",", ":")) + "\n")
    os.replace(tmp, out)
    return out, f"{nl} lines {len(rows)} rows trunc={trunc}"

def init(b, c): G["bys"] = b; G["ci"] = c

if __name__ == "__main__":
    a = sys.argv[1:]; procs = 3
    if "--procs" in a: k = a.index("--procs"); procs = int(a[k + 1]); del a[k:k + 2]
    outdir = a[0]; os.makedirs(outdir, exist_ok=True)
    jobs = []; BY = {}; CI = {}
    for rd in a[1:]:
        rd = rd.rstrip("/"); run = os.path.basename(rd); by = {}; ci = {}
        for l in open(rd + "/launches.jsonl"):
            try: j = json.loads(l); s = int(j["slot"]); mint = j["mint"]; ci[mint] = (s, int(j["idx"]))
            except Exception: continue
            by.setdefault(s, set()).add(mint); by.setdefault(s + 1, set()).add(mint)
        BY[run] = by; CI[run] = ci
        for fn in sorted(glob.glob(rd + "/txs/txs_*.jsonl.gz")): jobs.append((fn, outdir, run))
    print("jobs", len(jobs), flush=True)
    with Pool(procs, initializer=init, initargs=(BY, CI)) as P:
        for k, (o, msg) in enumerate(P.imap_unordered(one, jobs)):
            print(k, o.split("/")[-2][-13:], os.path.basename(o), msg, flush=True)
