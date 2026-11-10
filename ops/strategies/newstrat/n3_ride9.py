#!/usr/bin/env python3
"""NEWSTRAT ideas built on 9pQQ's / 8PgC's visible actions (signing time = when we see their landed tx; we land +D ms later).
  REPOS  : after the wallet SELLS a mint it has round-tripped >= K times there (K=1,2,3), buy at its sell + D
           ("pre-position for its re-entry"); exits: next buy by the wallet + D (sell into its buy + followers, cap 300 s),
           fixed holds, reactive TP with min-out, trailing stop.
  COPY   : buy at the wallet's buy + D ("ride its follow-on demand"); exits fixed 1/3/6/25 slots or its sell + D.
  RIDE   : buy at the wallet's FIRST (K=1) or SECOND (K=2) buy on the mint + D ("it started cycling = attention");
           exits: fixed 150/600 slots, trailing 20/30 %, attention end (no trade by it for 150 slots), its sell + D.
0.55 SOL, pump fee 1.25 % each way, 4.5 mSOL per round trip (~18 mSOL total), the wallet's trades kept on the tape.
Row 'f20' = 20 % of outside token buys in the 10 slots after our entry removed.
usage: n3_ride9.py WALLETNAME RUN [RUN ...]   -> OUT/n3_<wallet>_<run>.json"""
import sys, json
import numpy as np
import nlib as L
import xlib as X

DS = [0, 50, 70, 90]
CAP300 = 300_000.0
CAP600 = 600_000.0

def main(wname, run):
    w = {"9pQQ": L.W9, "8PgC": L.W8}[wname]
    t = L.load(run); uid = t.uix[w]
    trips = [x for x in json.load(open(f"{L.OUT}/trips_{run}.json"))[wname] if not x["may"]]
    by = {}
    for x in trips: by.setdefault(x["mint"], []).append(x)
    R = {}
    def add(key, v, vf):
        r = R.setdefault(key, [[], []]); r[0].append(v); r[1].append(vf)
    for m, xs in by.items():
        xs.sort(key=lambda x: x["cc0"])
        M = L.Mint(t, t.mix[m])
        own = M.U == uid
        bcc = M.CC[own & (M.TK > 0)]; acc = M.CC[own]
        for D in DS:
            def go(idea, t_in, exits):
                e, tok = X.entry(M, t_in)
                for ename, f in exits:
                    t_out = f(e, tok)
                    if t_out <= t_in: t_out = t_in + 1
                    v = L.trip(M, [t_in], [t_out])[0]
                    vf = L.trip(M, [t_in], [t_out], fol=L.FOLSHARE)[0] if D == 70 else v
                    add((idea, ename, D), v, vf)
            for k, x in enumerate(xs):
                # REPOS: entry at its sell of trip k (it has done k+1 round trips here)
                if x.get("x") is not None:
                    t_in = x["cc1"] + D
                    ex = [("next9buy_c300", lambda e, tok: X.ex_next(bcc, t_in - D, D, CAP300)[0]),
                          ("fix25", lambda e, tok: X.ex_fix(M, t_in, 25)),
                          ("fix150", lambda e, tok: X.ex_fix(M, t_in, 150)),
                          ("tp5_c150", lambda e, tok: X.ex_tp(M, t_in, e, tok, 0.05, D, 150 * X.SL)[0]),
                          ("tp10sl10_c600", lambda e, tok: X.ex_tp(M, t_in, e, tok, 0.10, D, CAP600, sl=0.10)[0]),
                          ("trail15_c600", lambda e, tok: X.ex_trail(M, t_in, e, tok, 0.15, D, CAP600)[0])]
                    for K in (1, 2, 3):
                        if k + 1 >= K: go(f"REPOS_K{K}", t_in, ex)
                # COPY: entry at its buy
                t_in = x["cc0"] + D
                ex = [("fix1", lambda e, tok: X.ex_fix(M, t_in, 1)), ("fix3", lambda e, tok: X.ex_fix(M, t_in, 3)),
                      ("fix6", lambda e, tok: X.ex_fix(M, t_in, 6)), ("fix25", lambda e, tok: X.ex_fix(M, t_in, 25))]
                if x.get("x") is not None:
                    ex.append(("itsell", lambda e, tok: x["cc1"] + D))
                go("COPY", t_in, ex)
                # RIDE: first / second buy on the mint
                if k in (0, 1):
                    ex = [("fix150", lambda e, tok: X.ex_fix(M, t_in, 150)), ("fix600", lambda e, tok: X.ex_fix(M, t_in, 600)),
                          ("trail20_c600", lambda e, tok: X.ex_trail(M, t_in, e, tok, 0.20, D, CAP600)[0]),
                          ("trail30_c600", lambda e, tok: X.ex_trail(M, t_in, e, tok, 0.30, D, CAP600)[0]),
                          ("attn150_c1800", lambda e, tok: X.ex_attn(acc, t_in - D, 150, 1_800_000.0) + D)]
                    if x.get("x") is not None:
                        ex.append(("itsell", lambda e, tok: x["cc1"] + D))
                    go(f"RIDE_K{k+1}", t_in, ex)
    hrs = L.hours(t)
    out = {"run": run, "hours": hrs, "rows": []}
    for (idea, ename, D), (v, vf) in sorted(R.items()):
        s = L.stats(v); s.update(idea=idea, exit=ename, D=D, per_day=round(s["net"] / hrs * 24, 2))
        if D == 70: s["f20_day"] = round(sum(vf) / 1e9 / hrs * 24, 2)
        out["rows"].append(s)
    json.dump(out, open(f"{L.OUT}/n3_{wname}_{run}.json", "w"))
    print(run, wname, "hours", round(hrs, 1), "mints", len(by), flush=True)

if __name__ == "__main__":
    for r in sys.argv[2:]: main(sys.argv[1], r)
