#!/usr/bin/env python3
"""INSIDER step 6: why the census paper does not survive the replay, and the cascade check (tape attribution of the replay's insider fills).
For each insider-window fill (all reps): the dump we filled on = the largest sell of the token from 1 slot before our fill to our fill
(who: the trigger insider / another create-slot insider / the creator / someone else); sells by other insiders / the creator / the trigger
insider inside our hold (our fill -> our sell's landing) = the cascade; joined with the census record of the trigger (paper mSOL).
usage: in6_explain.py CTX.pkl RUNDIR CENSUS.pkl VARIANT[,VARIANT] OUT.json"""
import sys, json, pickle, glob, collections
import numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/insider")
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/multiarm")
import ma_lib as M

ctxp, rundir, cenp, vs, outp = sys.argv[1:6]
ctx = pickle.load(open(ctxp, "rb"))
tape = M.Tape(ctx["tab"])
cen = pickle.load(open(cenp, "rb"))
cmap = {}
for r in cen:
    if r["class"] == "insider": cmap[(r["mint"], r["w"])] = r
SMS = 212.0
out = {}
for v in vs.split(","):
    rows = []
    for f in sorted(glob.glob(f"{rundir}/{v}__*.pkl")):
        d = pickle.load(open(f, "rb"))
        rows += [dict(r, rep=d["rep"]) for r in d["rows"] if r["kind"] == "ins"]
    nrep = len(glob.glob(f"{rundir}/{v}__*.pkl"))
    att = collections.defaultdict(lambda: [0, 0.0]); casc = collections.defaultdict(lambda: [0, 0.0]); paper = collections.defaultdict(lambda: [0, 0.0, 0.0])
    lag = []
    for r in rows:
        m = r["mint"]; t = tape.trades(m)
        c = tape.creates.get(m) or {}
        crea = {tape.gid.get(c.get("creator")), tape.gid.get(c.get("payer"))}
        s0 = c.get("slot")
        ins = set(int(u) for u, b, s in zip(t["user"], t["buy"], t["slot"]) if b and s == s0) - crea
        trig = r["ins_u"]
        wshort = tape.ids[trig][:8]
        cr = cmap.get((m, wshort))
        pv = cr["paper"] if cr else None
        key = "paper_fill" if pv is not None else ("insider_dumped_no_paper" if cr and cr["dump"] else "no_dump_50")
        paper[key][0] += 1
        if pv is not None: paper[key][1] += pv / 1e3
        paper[key][2] += r["cash"] if r["filled"] else r["cash"]
        if not r["filled"]: continue
        fs, fi = r["fs"], r["fi"]
        kf = np.searchsorted(t["slot"].astype(np.int64) * 100000 + t["idx"].astype(np.int64), fs * 100000 + fi)
        lo = np.searchsorted(t["slot"], fs - 1)
        best = None
        for q in range(lo, kf):
            if not t["buy"][q] and (best is None or t["tok"][q] > t["tok"][best]): best = q
        if best is None: who = "no_sell_before_fill"
        else:
            u = int(t["user"][best])
            who = "trigger_insider" if u == trig else ("other_insider" if u in ins else ("creator" if u in crea else "other_wallet"))
            lag.append(int(kf - best - 1))
        att[who][0] += 1; att[who][1] += r["cash"]
        # cascade: sells by the trigger insider / other insiders / the creator inside our hold (fill -> sell landing)
        ss = int(r["c_sell"] // SMS)
        hi = np.searchsorted(t["slot"], ss + 1)
        cs = [q for q in range(kf, hi) if not t["buy"][q] and int(t["user"][q]) not in tape.ours and (int(t["user"][q]) in ins or int(t["user"][q]) in crea)]
        tag = "insider_or_creator_sold_in_hold" if cs else "clean_hold"
        casc[tag][0] += 1; casc[tag][1] += r["cash"]
    nf = sum(a[0] for a in att.values())
    out[v] = {"reps": nrep, "ins_windows_per_rep": round(len(rows) / max(nrep, 1), 1), "fills_per_rep": round(nf / max(nrep, 1), 1),
              "dump_we_filled_on": {k: {"fills_per_rep": round(a[0] / nrep, 1), "share": round(a[0] / max(nf, 1), 3), "sol_per_rep": round(a[1] / nrep, 3),
                                        "mSOL_per_fill": round(a[1] / max(a[0], 1) * 1e3, 1)} for k, a in att.items()},
              "trades_between_dump_and_our_fill_median": float(np.median(lag)) if lag else None,
              "cascade": {k: {"fills_per_rep": round(a[0] / nrep, 1), "share": round(a[0] / max(nf, 1), 3), "sol_per_rep": round(a[1] / nrep, 3),
                              "mSOL_per_fill": round(a[1] / max(a[0], 1) * 1e3, 1)} for k, a in casc.items()},
              "by_census_outcome": {k: {"windows_per_rep": round(a[0] / nrep, 1), "census_paper_sol": round(a[1] / nrep, 2), "replay_sol_per_rep": round(a[2] / nrep, 3)}
                                    for k, a in paper.items()}}
json.dump(out, open(outp, "w"), indent=1)
print(json.dumps(out, indent=1))
