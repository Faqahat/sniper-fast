#!/usr/bin/env python3
"""9pQQ step 1: every tx SIGNED by 9pQQ (from botpnl9 pass-1 files), one compact row each -> own_<run>.pkl.
Row: s, i, bt, sig, err (str or None), kind (buy/sell/close/fail/other), mint, tok, sol (lamport delta incl. fees/tips/rent),
fee, cup, cul, cu, tips [(acct, lamports)], progs (short), ixn.  Read-only on the inputs.
usage: a1_own.py"""
import json, glob, os, pickle, collections
W = "9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN"
IN = "/home/moiz/sniper-data/botpnl9"
OUT = "/home/moiz/sniper-data/rivals/9pQQ"
RUNS = ["run_20261028_1405", "run_20261030_1355", "run_20261031_1350", "run_20261102_1250"]

for r in RUNS:
    rows = []
    for fn in sorted(glob.glob(f"{IN}/{r}/p1_*.jsonl")):
        for l in open(fn, errors="replace"):
            if W not in l: continue
            d = json.loads(l)
            if W not in (d.get("signers") or []): continue
            mm = collections.Counter()
            for m, own, pre, post in d.get("tb") or []:
                if own == W: mm[m] += (post or 0) - (pre or 0)
            m = max(mm, key=lambda k: abs(mm[k])) if mm else ((d.get("mints") or [None])[0])
            tok = mm.get(m, 0)
            ixn = d.get("ixn") or []
            if d.get("err") is not None: kind = "fail"
            elif tok > 0: kind = "buy"
            elif tok < 0: kind = "sell"
            elif ixn and all(x == "CloseAccount" for x in ixn): kind = "close"
            else: kind = "other"
            rows.append(dict(s=d["s"], i=d.get("i") or 0, bt=d.get("bt"), sig=d["sig"], err=None if d.get("err") is None else json.dumps(d["err"]),
                             kind=kind, mint=m, tok=tok, sol=dict((a, v) for a, v in d.get("sd") or []).get(W, 0), fee=d.get("fee"),
                             cup=d.get("cup"), cul=d.get("cul"), cu=d.get("cu"), tips=d.get("tips") or [],
                             progs=[p[:6] for p in d.get("progs") or []], ixn=ixn, nsig=len(d.get("signers") or []),
                             sd=[(a, v) for a, v in d.get("sd") or [] if a != W]))
    rows.sort(key=lambda x: (x["s"], x["i"]))
    pickle.dump(rows, open(f"{OUT}/own_{r}.pkl", "wb"))
    c = collections.Counter(x["kind"] for x in rows)
    print(r, len(rows), dict(c), {k: round(sum(x["sol"] for x in rows if x["kind"] == k) / 1e9, 3) for k in c})
