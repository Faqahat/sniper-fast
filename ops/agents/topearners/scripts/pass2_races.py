#!/usr/bin/env python3
# PASS 2 (read-only): race table. For every sell >= 1 SOL on a curve: the dump + every buy by another wallet in the
# next 5 slots (chain order), with each buyer's tx economics. Plus per-lot FIFO outcomes for a set of focus wallets.
# usage: pass2_races.py <focus_wallets.txt> <out_races.jsonl.gz> <out_lots.jsonl.gz> [procs]
import os, sys, json, gzip, glob, zlib, collections
from multiprocessing import Pool
D = "/home/moiz/sniper-data/collect"
RUNS = [("R2", "phaseA_selfwd"), ("R3", "phaseA_r3day")]
DSLOT = 5; BIG = 1_000_000_000
FOCUS = set(l.strip() for l in open(sys.argv[1]) if l.strip())

def load_bucket(pa, b):
    T = {}
    for f in sorted(glob.glob(os.path.join(D, pa, f"b{b:03d}", "*.jsonl.gz"))):
        try:
            for line in gzip.open(f, "rt"):
                if line[2] == "T":
                    r = json.loads(line)
                    if r[12]: continue
                    T[(r[5], r[13])] = r
        except (EOFError, OSError, zlib.error): pass
    return T

def work(b):
    races = []; lots_out = []
    for tag, pa in RUNS:
        T = load_bucket(pa, b)
        nev = collections.Counter(k[0] for k in T)
        bym = collections.defaultdict(list)
        for k, r in T.items(): bym[r[1]].append(r)
        for m, tr in bym.items():
            tr.sort(key=lambda r: (r[2], r[3], r[13]))
            n = len(tr)
            for k, r in enumerate(tr):
                if r[15] == 1 or r[16] < BIG: continue
                s0 = r[2]; seller = r[14]
                buys = []; nsells_between = 0
                for q in tr[k + 1:]:
                    if q[2] - s0 > DSLOT: break
                    if q[15] == 1:
                        if q[14] == seller: continue
                        buys.append([q[14], q[2] - s0, q[3], q[13], q[5], q[6], q[16], q[17], q[7], q[8], q[9], q[10], q[11], q[18], q[19], nev[q[5]], nsells_between])
                    else: nsells_between += 1
                    if len(buys) >= 40: break
                pv = tr[k - 1] if k > 0 else None
                races.append(dict(run=tag, m=m, s=s0, i=r[3], j=r[13], sig=r[5], user=seller, payer=r[6], sol=r[16], tok=r[17],
                                  vsol=r[18], vtok=r[19], fee=r[7], cup=r[8], tips=r[11], bt=r[4], pre=[pv[18], pv[19]] if pv else None,
                                  fb=(r[22] or 95) + (r[23] or 30), buys=buys))
            # FIFO lots for focus wallets
            lots = collections.defaultdict(collections.deque)
            last_big = []
            for r in tr:
                (_, _, s, i, bt, sig, payer, fee, cup, cul, cu, tips, err, j, user, buy, sol, tok, vsol, vtok, fl, cfl, fbps, cbps) = r
                if buy != 1 and sol >= BIG: last_big.append((s, user, i, sig, sol))
                if user not in FOCUS: continue
                txc = ((fee or 0) + (tips or 0)) / nev[sig]
                if buy == 1:
                    trig = None
                    for bb in reversed(last_big):
                        if s - bb[0] > DSLOT: break
                        if bb[1] != user: trig = bb; break
                    L = dict(run=tag, w=user, m=m, s=s, i=i, bt=bt, sig=sig, payer=payer, sol=sol, tok=tok, fee=fee, cup=cup, cul=cul, cu=cu, tips=tips,
                             vsol=vsol, vtok=vtok, cost=sol + (fl or 0) + (cfl or 0) + txc, trig=[trig[0], trig[2], trig[3], trig[4], trig[1]] if trig else None,
                             left=tok, got=0.0, sells=[], pnl=None)
                    lots[user].append(L); lots_out.append(L)
                else:
                    proceeds = sol - (fl or 0) - (cfl or 0) - txc
                    left = tok; dq = lots[user]
                    while left > 0 and dq:
                        L = dq[0]; take = min(left, L["left"])
                        L["got"] += proceeds * take / tok; L["left"] -= take; left -= take
                        L["sells"].append([s, i, sig, take, sol * take / tok, fee, cup, tips])
                        if L["left"] <= 0:
                            dq.popleft(); L["pnl"] = L["got"] - L["cost"]
            lastr = tr[-1]
            for w, dq in lots.items():
                for L in dq:
                    Vl, Tl = lastr[18], lastr[19]
                    mv = (Vl * L["left"] / (Tl + L["left"]) * 0.9875) if Tl else 0.0
                    L["open_mv"] = mv; L["pnl_mtm"] = L["got"] + mv - L["cost"]
    return b, races, lots_out

if __name__ == "__main__":
    out_r, out_l = sys.argv[2], sys.argv[3]; procs = int(sys.argv[4]) if len(sys.argv) > 4 else 4
    fr = gzip.open(out_r, "wt", compresslevel=3); fl = gzip.open(out_l, "wt", compresslevel=3)
    nr = nl = 0
    with Pool(procs) as p:
        for k, (b, races, lots) in enumerate(p.imap_unordered(work, range(256)), 1):
            for r in races: fr.write(json.dumps(r, separators=(",", ":")) + "\n")
            for L in lots: fl.write(json.dumps(L, separators=(",", ":")) + "\n")
            nr += len(races); nl += len(lots)
            if k % 32 == 0: print(k, nr, nl, flush=True)
    fr.close(); fl.close(); print("DONE", nr, nl)
