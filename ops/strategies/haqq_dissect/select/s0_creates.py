#!/usr/bin/env python3
"""SELECT step 0 (read-only on the raw recordings): every successful pump.fun create tx with the CreateEvent STRINGS (name, symbol,
uri) that presend/real/decode.py skips, plus the create tx's shape: fee, CU used / price / limit, programs, instruction names,
signers, tips, the payer's SOL delta, and the creator's initial buy inside the create tx (TradeEvent rows of the same tx).
No URL is fetched: the uri is only parsed as a string (host / path pattern).
Usage: s0_creates.py [--procs 2]. Out: sniper-data/haqq_dissect/select/cr/<chunk>.jsonl (+ .done), merged by s1."""
import sys, os, glob, json, base64, hashlib, subprocess, struct, time
from multiprocessing import Pool
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real")
import decode as D
OUT = "/home/moiz/sniper-data/haqq_dissect/select/cr"
REC = "/home/moiz/sniper-data/collect"


def strings_of(raw):
    r = D.Rd(raw, 8)
    try:
        name = r.st(); sym = r.st(); uri = r.st(); mint = r.pk(); _bc = r.pk(); user = r.pk(); creator = r.pk()
        return dict(name=name, sym=sym, uri=uri, mint=mint, user=user, creator=creator)
    except Exception as ex:
        return dict(err=str(ex)[:60])


def one(fn):
    out = os.path.join(OUT, os.path.basename(os.path.dirname(os.path.dirname(fn))) + "__" + os.path.basename(fn).replace(".jsonl.gz", ".jsonl"))
    if os.path.exists(out + ".done"): return fn, "cached"
    n = 0
    p = subprocess.Popen(f"zcat '{fn}' 2>/dev/null | grep -F '\"Create'", shell=True, stdout=subprocess.PIPE, text=True, bufsize=1 << 20)
    with open(out, "w") as f:
        for line in p.stdout:
            try: r = json.loads(line)
            except Exception: continue
            if r.get("err") is not None: continue
            ixn = r.get("ixn") or []
            if not any(x in ("Create", "CreateV2") for x in ixn): continue
            ev = None; buys = []
            for b in D.chunks_of(r.get("ev")):
                if b[:8] == D.CREATE_EV and ev is None: ev = strings_of(b)
                elif b[:8] == D.DISC:
                    t = D.parse_trade(b)
                    if t: buys.append((t[0], t[1], t[2], t[3], t[4]))
            if not ev or "mint" not in ev: continue
            sg = r.get("signers") or []
            sd = {a: v for a, v in (r.get("sd") or [])}
            rec = dict(s=r["s"], i=r["i"], bt=r["bt"], sig=r["sig"], fee=r.get("fee"), cu=r.get("cu"), cup=r.get("cup"), cul=r.get("cul"),
                       signers=sg, progs=r.get("progs"), ixn=ixn, tips=r.get("tips"), payer_sd=sd.get(sg[0]) if sg else None,
                       nsd=len(sd), buys=[(m, s_, t_, bu, u) for m, s_, t_, bu, u in buys], **ev)
            f.write(json.dumps(rec) + "\n"); n += 1
    p.wait()
    open(out + ".done", "w").write(str(n))
    return fn, n


def main():
    procs = 2
    if "--procs" in sys.argv: procs = int(sys.argv[sys.argv.index("--procs") + 1])
    os.makedirs(OUT, exist_ok=True)
    files = sorted(glob.glob(f"{REC}/run_*/txs/txs_*.jsonl.gz"))
    now = time.time(); files = [f for f in files if now - os.path.getmtime(f) > 240]
    t0 = time.time(); tot = 0
    with Pool(procs) as P:
        for k, (fn, n) in enumerate(P.imap_unordered(one, files)):
            if n != "cached": tot += n
            if k % 50 == 0: print(f"{k}/{len(files)} {os.path.basename(fn)} {n} creates (total {tot:,}) {time.time() - t0:.0f}s", flush=True)
    print("DONE", len(files), tot, f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
