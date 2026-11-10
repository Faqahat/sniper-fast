#!/usr/bin/env python3
"""CASEBOOK step 0: 9pQQ's own txs -> actions + trips per run.
in : lanes/own_raw_<run>.jsonl (or a dir of own/*.jsonl from the lanes tape)
out: casebook/own_<run>.jsonl (one row per own tx: s,i,bt,sig,err,kind,mint,dtok,dsol,vsol,vtok)
     casebook/trips_<run>.jsonl (buy->sell pairs per mint, net incl. ATA rent refund 1,513,840 when ATA created)
usage: c0_own.py RUN [src ...]"""
import sys, json, glob, os, base64, struct
W = "9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN"
OUT = "/home/it/sniper-data/rivals/9pQQ/casebook"
def evs(d):
    r = []
    for e in d.get("ev") or []:
        b = base64.b64decode(e)
        if b[:8].hex() != "bddb7fd34ee661ee" or len(b) < 129: continue
        sol, tok = struct.unpack_from("<QQ", b, 40); buy = b[56] == 1
        vsol, vtok, rsol, rtok = struct.unpack_from("<QQQQ", b, 97)
        r.append((buy, sol, tok, vsol, vtok))
    return r
run = sys.argv[1]; srcs = sys.argv[2:]
files = []
for s in srcs: files += sorted(glob.glob(s + "/*.jsonl")) if os.path.isdir(s) else [s]
seen = set(); rows = []
for fn in files:
    for l in open(fn, errors="replace"):
        d = json.loads(l)
        if (d.get("signers") or [None])[0] != W or d["sig"] in seen: continue
        seen.add(d["sig"]); ix = d.get("ixn") or []
        kind = "buy" if any(x.startswith("Buy") for x in ix) else ("sell" if any(x.startswith("Sell") for x in ix) else "other")
        mint = (d.get("mints") or [None])[0]
        dtok = 0
        for mm, ow, pre, post in d.get("tb") or []:
            if ow == W and mm == mint: dtok += (post or 0) - (pre or 0)
        dsol = dict(d.get("sd") or []).get(W, 0)
        e = evs(d); vsol = e[0][3] if e else None; vtok = e[0][4] if e else None
        ata = any(x == "InitializeAccount3" for x in ix)
        rows.append(dict(s=d["s"], i=d.get("i") or 0, bt=d.get("bt"), sig=d["sig"], err=d.get("err") is not None, kind=kind, mint=mint,
                         dtok=dtok, dsol=dsol, vsol=vsol, vtok=vtok, ata=ata, nm=len(d.get("mints") or []), ixn=ix))
rows.sort(key=lambda r: (r["s"], r["i"]))
with open(f"{OUT}/own_{run}.jsonl", "w") as fo:
    for r in rows: fo.write(json.dumps(r) + "\n")
open_ = {}; trips = []; bad = 0
for r in rows:
    if r["err"] or r["kind"] == "other": continue
    m = r["mint"]
    if r["kind"] == "buy":
        if m in open_: bad += 1
        open_[m] = r
    else:
        b = open_.pop(m, None)
        if b is None: bad += 1; continue
        net = b["dsol"] + r["dsol"] + (1513840 if b["ata"] else 0)
        trips.append(dict(mint=m, bs=b["s"], bi=b["i"], bbt=b["bt"], ss=r["s"], si=r["i"], sbt=r["bt"], hold=r["s"] - b["s"],
                          net=net, bvsol=b["vsol"], bvtok=b["vtok"], svsol=r["vsol"], svtok=r["vtok"], cost=-b["dsol"]))
with open(f"{OUT}/trips_{run}.jsonl", "w") as fo:
    for t in trips: fo.write(json.dumps(t) + "\n")
print(run, "txs", len(rows), "trips", len(trips), "open", len(open_), "unpaired", bad, "net SOL", round(sum(t["net"] for t in trips) / 1e9, 2),
      "failed buys", sum(1 for r in rows if r["err"] and r["kind"] == "buy"), "failed sells", sum(1 for r in rows if r["err"] and r["kind"] == "sell"))
