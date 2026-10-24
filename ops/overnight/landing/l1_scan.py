#!/usr/bin/env python3
# LANDING-PATH STUDY, step 1 (READ-ONLY, offline, local files only).
# Scan the raw collector chunks (txs/*.jsonl.gz) of one or more runs and keep, for every launch in launches.jsonl,
# every recorded tx that touches the new mint in the create slot S .. S+DMAX (OK and failed), in a compact form:
#   tips recomputed from the balance deltas with the current tipmap, decoded pump.fun TradeEvents of that mint,
#   fee / CU price / CU limit / signers / instruction names / programs.
# Also keeps per-slot "max tx index seen" (a lower bound on the block's tx count, used for create-position-in-slot).
# usage: python3 -I l1_scan.py <out_dir> <procs> <run_dir> [<run_dir> ...]
import sys, os, json, gzip, base64, zlib, glob, collections
from multiprocessing import Pool

OUT = sys.argv[1]; PROCS = int(sys.argv[2]); RUNS = sys.argv[3:]
DMAX = 4
TIPMAP = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
TRADE = bytes([189, 219, 127, 211, 78, 230, 97, 238])
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n:
        n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))


def tip_service(acct):
    s = TIPMAP.get(acct)
    if s: return s
    if acct.startswith("noz"): return "nozomi"
    return None


CBS = {}   # run tag -> {slot: [(mint, mint_bytes)]}
for rd in RUNS:
    tag = os.path.basename(rd.rstrip("/"))
    d = collections.defaultdict(list)
    with open(os.path.join(rd, "launches.jsonl")) as f:
        for line in f:
            try: L = json.loads(line)
            except Exception: continue
            if L.get("mint") and L.get("slot"):
                d[L["slot"]].append((L["mint"], L["mint"].encode()))
    CBS[tag] = dict(d)


def lines(path):
    # chunks cut by a restart / still being written are truncated: keep everything before the cut
    try:
        with gzip.open(path, "rb") as f:
            for line in f: yield line
    except (EOFError, OSError, zlib.error):
        return


def work(job):
    tag, path = job
    cbs = CBS[tag]
    name = f"{tag}__{os.path.basename(path).split('.')[0]}"
    out_tmp = os.path.join(OUT, "recs", name + ".jsonl.gz.tmp")
    fo = gzip.open(out_tmp, "wt", compresslevel=3)
    smax = {}; scnt = collections.Counter(); n = nk = bad = 0
    for line in lines(path):
        n += 1
        if not line.startswith(b'{"s":'):
            bad += 1; continue
        try:
            p = line.index(b",", 5); s = int(line[5:p])
            p2 = line.index(b",", p + 5); i = int(line[p + 5:p2])
        except ValueError:
            bad += 1; continue
        if i > smax.get(s, -1): smax[s] = i
        scnt[s] += 1
        hits = []
        for d in range(DMAX + 1):
            for m, mb in cbs.get(s - d, ()):
                if mb in line: hits.append((m, d))
        if not hits: continue
        try: r = json.loads(line)
        except Exception:
            bad += 1; continue
        # decode trade events once
        evs = []
        for e in r.get("ev") or []:
            try: raw = base64.b64decode(e + "=" * (-len(e) % 4))
            except Exception: continue
            if raw[:8] != TRADE or len(raw) < 113: continue
            u = lambda o: int.from_bytes(raw[o:o + 8], "little")
            evs.append((b58(raw[8:40]), raw[56], b58(raw[57:89]), u(40), u(48), u(97), u(105)))
        sd = r.get("sd") or []
        tips = {}
        for k, dl in sd:
            if dl > 0:
                sv = tip_service(k)
                if sv: tips[k] = [sv, k, dl]
        for k, dl in r.get("tips") or []:
            if k not in tips and dl > 0: tips[k] = [tip_service(k) or "unknown_tip", k, dl]
        signers = r.get("signers") or []
        payer = signers[0] if signers else None
        pd = None
        for k, dl in sd:
            if k == payer: pd = dl; break
        mints = set(r.get("mints") or [])
        for m, d in hits:
            mev = [[e[1], e[2], e[3], e[4], e[5], e[6]] for e in evs if e[0] == m]
            if m not in mints and not mev: continue
            rec = dict(run=tag, m=m, d=d, s=s, i=i, bt=r.get("bt"), sig=r["sig"], err=(None if r.get("err") is None else json.dumps(r["err"], separators=(",", ":"))[:120]),
                       fee=r.get("fee"), cu=r.get("cu"), cup=r.get("cup"), cul=r.get("cul"), ns=len(signers), sg=signers[:4],
                       ixn=r.get("ixn") or [], progs=r.get("progs") or [], tips=list(tips.values()), pd=pd, ev=mev,
                       nev_other=sum(1 for e in evs if e[0] != m), nm=len(mints))
            fo.write(json.dumps(rec, separators=(",", ":")) + "\n"); nk += 1
    fo.close()
    os.replace(out_tmp, out_tmp[:-4])
    with open(os.path.join(OUT, "slots", name + ".json"), "w") as f:
        json.dump({str(k): [v, scnt[k]] for k, v in smax.items()}, f, separators=(",", ":"))
    return name, n, nk, bad


if __name__ == "__main__":
    os.makedirs(os.path.join(OUT, "recs"), exist_ok=True); os.makedirs(os.path.join(OUT, "slots"), exist_ok=True)
    jobs = []
    for rd in RUNS:
        tag = os.path.basename(rd.rstrip("/"))
        for p in sorted(glob.glob(os.path.join(rd, "txs", "*.jsonl.gz"))):
            name = f"{tag}__{os.path.basename(p).split('.')[0]}"
            if os.path.exists(os.path.join(OUT, "recs", name + ".jsonl.gz")) and os.path.exists(os.path.join(OUT, "slots", name + ".json")):
                continue   # resumable
            jobs.append((tag, p))
    # biggest first for better packing
    jobs.sort(key=lambda j: -os.path.getsize(j[1]))
    print(f"{len(jobs)} chunks to scan", flush=True)
    tot = totk = totb = 0
    with Pool(PROCS) as pool:
        for k, (name, n, nk, bad) in enumerate(pool.imap_unordered(work, jobs), 1):
            tot += n; totk += nk; totb += bad
            if k % 10 == 0 or k == len(jobs):
                print(f"{k}/{len(jobs)} chunks, {tot} lines, {totk} kept, {totb} bad", flush=True)
    print("SCAN DONE", tot, totk, totb, flush=True)
