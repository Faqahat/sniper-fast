#!/usr/bin/env python3
# Loader for the non-SOL-quoted universe (read-only, offline). Builds a cache (data/ns_cache.pkl):
#   CR  {mint: create info}                       every collected launch's CreateEvent (quote, initial virtual quote reserves, mayhem)
#   L   {mint: launches.jsonl record + run}       collector launch list (both runs)
#   TR  {mint: [trades in chain order]}           non-SOL TradeEvents of launches in L whose quote != SOL
#   W   {sig: tx meta}                            payer SOL delta, tips, fee, programs, ix names of every tx with a non-SOL trade
# Trade dict keys mirror rp.read_bucket so rp-style code works: sol := net quote amount, vsol := virtual quote reserves
# (both in raw quote units), tok / vtok in raw token units.
import os, sys, json, gzip, glob, pickle, collections
HERE = "/home/moiz/sniper/ops/overnight/nonsol"; DATA = os.path.join(HERE, "data"); CACHE = os.path.join(DATA, "ns_cache.pkl")
D = "/home/moiz/sniper-data/collect"
RUNS = {"R1": "run_20261021_2207", "R2": "run_20261022_1543"}
WSOL = "So11111111111111111111111111111111111111112"
QN = {"pumpCmXqMfrsAkQ5r49WcJnRayYRqmXz6ae8H7H9Dfn": "PUMP", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
      "USD1ttGY1N17NEEHLmELoaybftRBUSErhqYiQzvEmuB": "USD1", "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT"}
PKT = 5 * 3600
def qname(q): return QN.get(q, q[:6])
def load_launches():
    L = {}
    for tag, run in RUNS.items():
        for l in open(os.path.join(D, run, "launches.jsonl")):
            try: c = json.loads(l)
            except Exception: continue
            if c["mint"] not in L: c["run"] = tag; L[c["mint"]] = c
    return L
def build():
    L = load_launches(); CR = {}; TRr = collections.defaultdict(list); W = {}
    for run in RUNS:
        for f in sorted(glob.glob(os.path.join(DATA, "raw_" + run, "*.jsonl.gz"))):
            for line in gzip.open(f, "rt"):
                r = json.loads(line)
                if r[0] == "C":
                    _, m, s, i, bt, sig, quote, vq0, vtok0, mayhem, b73, x114, tail, user, creator = r
                    if m not in CR: CR[m] = dict(run=run, s=s, i=i, bt=bt, sig=sig, quote=quote, vq0=vq0, vtok0=vtok0, mayhem=mayhem, b73=b73, x114=x114, tail=tail, user=user, creator=creator)
                elif r[0] == "T": TRr[r[1]].append(r)
                elif r[0] == "W":
                    _, sig, s, i, payer, sdp, tips, fee, cu, progs, ixn, tb, nsig = r
                    W[sig] = dict(payer=payer, sdp=sdp, tips=tips, fee=fee, cu=cu, progs=progs, ixn=ixn, nsig=nsig)
    TR = {}
    for m, rows in TRr.items():
        if m not in L: continue
        seen = set(); out = []
        for r in rows:
            (_, _, s, i, bt, sig, j, user, isbuy, tok, vtok, rtok, qm, q, vq, rq, fbps, fee, cbps, cfee, ixname, e17, e25) = r
            if (sig, j) in seen: continue
            seen.add((sig, j))
            out.append(dict(s=s, i=i, j=j, bt=bt, sig=sig, user=user, buy=isbuy == 1, tok=tok, vtok=vtok, rtok=rtok, qm=qm, sol=q, vsol=vq, rq=rq,
                            fbps=fbps, cbps=cbps, feeq=fee, cfeeq=cfee, ix=ixname, e17=e17, e25=e25))
        out.sort(key=lambda t: (t["s"], t["i"], t["j"]))
        TR[m] = out
    pickle.dump(dict(L=L, CR=CR, TR=TR, W=W), open(CACHE + ".tmp", "wb"), protocol=4); os.rename(CACHE + ".tmp", CACHE)
    return L, CR, TR, W
def load():
    if not os.path.exists(CACHE): return build()
    d = pickle.load(open(CACHE, "rb")); return d["L"], d["CR"], d["TR"], d["W"]
if __name__ == "__main__":
    L, CR, TR, W = build()
    print("launches", len(L), "creates decoded", len(CR), "in L", sum(1 for m in CR if m in L), "non-SOL trade mints in L", len(TR), "W", len(W))
