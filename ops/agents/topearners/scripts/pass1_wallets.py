#!/usr/bin/env python3
# PASS 1 (read-only): per-wallet FIFO realized P&L from decoded phaseA trade rows, with every buy tagged
# "dip" if a >= 1 SOL sell by ANOTHER wallet on the same mint happened at most DSLOT slots before it (and earlier in chain order).
# Costs: buy = sol + pump fee + creator fee + tx fee/tips share; sell proceeds = sol - pump fee - creator fee - tx fee/tips share.
# Failed txs (X rows, err) are charged to their fee payer.
# usage: pass1_wallets.py <out.json> [procs]
import os, sys, json, gzip, glob, zlib, collections
from multiprocessing import Pool
D = "/home/moiz/sniper-data/collect"
RUNS = [("R2", "phaseA_selfwd"), ("R3", "phaseA_r3day")]
DSLOT = 5; BIG = 1_000_000_000
PKT = 5 * 3600

def load_bucket(pa, b):
    T = {}; X = {}
    for f in sorted(glob.glob(os.path.join(D, pa, f"b{b:03d}", "*.jsonl.gz"))):
        try:
            for line in gzip.open(f, "rt"):
                if line[2] == "T":
                    r = json.loads(line)
                    if r[12]: continue
                    T[(r[5], r[13])] = r
                elif line[2] == "X":
                    if not line.rstrip().endswith("]]"): pass
                    r = json.loads(line)
                    if r[12]: X[r[5]] = r
        except (EOFError, OSError, zlib.error): pass
    return T, X

def newagg():
    return dict(nb=0, nbd=0, ns=0, solb=0, solbd=0, pnl=0, pnld=0, pnlnd=0, lotsd=0, winsd=0, lotsnd=0, winsnd=0,
                txc=0, tips=0, nf=0, ff=0, openc=0, opencd=0, unm=0, unm_sol=0, mintsd=set(), hd=collections.Counter(),
                hall=collections.Counter(), ds=collections.Counter(), nbtip=0, cupsum=0, ncup=0, holdd=[] , runs=collections.Counter(), mtm=0.0, mtmd=0.0, nopend=0, mtmdneg=0.0, first=0, didx=collections.Counter(), day=0.0, night=0.0)

def work(arg):
    b = arg
    A = collections.defaultdict(newagg)
    for tag, pa in RUNS:
        T, X = load_bucket(pa, b)
        for sig, r in X.items():
            a = A[r[6]]; a["nf"] += 1; a["ff"] += r[7] or 0
        # events per tx (for cost sharing)
        nev = collections.Counter(k[0] for k in T)
        bym = collections.defaultdict(list)
        for k, r in T.items(): bym[r[1]].append(r)
        for m, tr in bym.items():
            tr.sort(key=lambda r: (r[2], r[3], r[13]))
            lots = collections.defaultdict(collections.deque)   # wallet -> deque of [tok_left, cost_left, dip, dslot, s, bt, pnl_acc, tok0]
            last_big = []   # recent big sells (s, user)
            for r in tr:
                (_, _, s, i, bt, sig, payer, fee, cup, cul, cu, tips, err, j, user, buy, sol, tok, vsol, vtok, fl, cfl, fbps, cbps) = r
                txc = ((fee or 0) + (tips or 0)) / nev[sig]
                a = A[user]; a["txc"] += txc; a["tips"] += (tips or 0) / nev[sig]; a["runs"][tag] += 1
                h = (bt + PKT) // 3600 if bt else None
                if buy == 1:
                    a["nb"] += 1; a["solb"] += sol
                    if tips: a["nbtip"] += 1
                    if cup: a["cupsum"] += cup; a["ncup"] += 1
                    dslot = None; trig = None
                    for bb in reversed(last_big):
                        if s - bb[0] > DSLOT: break
                        if bb[1] != user: dslot = s - bb[0]; trig = bb; break
                    dip = dslot is not None
                    if dip:
                        a["nbd"] += 1; a["solbd"] += sol; a["mintsd"].add(m); a["ds"][dslot] += 1
                        if trig[3] == 0: a["first"] += 1
                        if dslot == 0: a["didx"][min(i - trig[2], 999) // 50 * 50] += 1
                    if last_big: last_big[-1][3] += 1
                    cost = sol + (fl or 0) + (cfl or 0) + txc
                    if tok > 0: lots[user].append([tok, cost, dip, dslot, s, bt, 0.0, tok, cost])
                else:
                    a["ns"] += 1
                    if sol >= BIG: last_big.append([s, user, i, 0])
                    proceeds = sol - (fl or 0) - (cfl or 0) - txc
                    left = tok; dq = lots[user]
                    while left > 0 and dq:
                        L = dq[0]; take = min(left, L[0]); frac = take / L[0]
                        c = L[1] * frac; p = proceeds * (take / tok)
                        L[6] += p - c; L[0] -= take; L[1] -= c; left -= take
                        if L[0] <= 0:
                            dq.popleft()
                            pn = L[6]; a["pnl"] += pn
                            hb = (L[5] + PKT) // 3600 if L[5] else None
                            a["hall"][hb] += pn
                            if L[2]:
                                a["pnld"] += pn; a["lotsd"] += 1; a["winsd"] += pn > 0; a["hd"][hb] += pn
                                if hb is not None:
                                    if 9 <= hb % 24 < 21: a["day"] += pn
                                    else: a["night"] += pn
                                if len(a["holdd"]) < 400: a["holdd"].append(s - L[4])
                            else:
                                a["pnlnd"] += pn; a["lotsnd"] += 1; a["winsnd"] += pn > 0
                    if left > 0:
                        a["unm"] += 1; a["unm_sol"] += proceeds * (left / tok)
            lastr = tr[-1]; Vl, Tl = lastr[18], lastr[19]; frl = ((lastr[22] or 95) + (lastr[23] or 30)) / 1e4
            for w, dq in lots.items():
                for L in dq:
                    a = A[w]
                    # open (or partially sold) lot: realized part + mark-to-market of the rest at the mint's last curve state
                    mv = (Vl * L[0] / (Tl + L[0]) * (1 - frl)) if Tl else 0.0
                    a["pnl"] += L[6]; a["openc"] += L[1]; a["mtm"] += mv - L[1]
                    if L[2]:
                        a["pnld"] += L[6]; a["opencd"] += L[1]; a["mtmd"] += mv - L[1]; a["nopend"] += 1
                        a["mtmdneg"] += min(0.0, mv - L[1])
                    else: a["pnlnd"] += L[6]
    out = {}
    for w, a in A.items():
        if a["nbd"] == 0 and a["nf"] < 50 and abs(a["pnl"]) < 1e9: continue
        a["mintsd"] = len(a["mintsd"]); a["hd"] = dict(a["hd"]); a["hall"] = dict(a["hall"]); a["ds"] = dict(a["ds"]); a["runs"] = dict(a["runs"]); a["didx"] = dict(a["didx"])
        out[w] = a
    return b, out

def merge(dst, src):
    for k, v in src.items():
        if k not in dst: dst[k] = v; continue
        if isinstance(v, dict):
            for kk, vv in v.items(): dst[k][kk] = dst[k].get(kk, 0) + vv
        elif isinstance(v, list): dst[k] = (dst[k] + v)[:400]
        else: dst[k] += v

if __name__ == "__main__":
    out, procs = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 4
    W = {}
    with Pool(procs) as p:
        for k, (b, o) in enumerate(p.imap_unordered(work, range(256)), 1):
            for w, a in o.items():
                if w not in W: W[w] = a
                else: merge(W[w], a)
            if k % 16 == 0: print(k, len(W), flush=True)
    for w, a in W.items():
        a["hd"] = {str(k): v for k, v in a["hd"].items()}; a["hall"] = {str(k): v for k, v in a["hall"].items()}; a["ds"] = {str(k): v for k, v in a["ds"].items()}; a["didx"] = {str(k): v for k, v in a["didx"].items()}
    json.dump(W, open(out, "w"))
    print("DONE", len(W))
