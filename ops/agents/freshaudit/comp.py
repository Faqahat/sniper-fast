#!/usr/bin/env python3
# per dump (sell >= 0.5 SOL, ok): what happened in the next slots on that mint (who bought, where, through which path)
# usage: comp.py <run tag r2|r3> <run dir> <out jsonl.gz>
import sys, os, json, gzip, glob, collections
from multiprocessing import Pool
sys.path.insert(0, "/home/moiz/sniper/ops/agents/freshaudit")
from load import chunks, relays, tipsum, trade_of, is_buy_attempt, OURS
RUN, RUNDIR, OUTP = sys.argv[1], sys.argv[2], sys.argv[3]
LAUNCH = {}
for l in open(os.path.join(RUNDIR, "launches.jsonl")):
    try: c = json.loads(l)
    except Exception: continue
    LAUNCH.setdefault(c["mint"], (c["slot"], c.get("bt"), c.get("creator") or c.get("user")))
def work(f):
    D = []; F = []; SL = {}
    for line in gzip.open(f, "rt"):
        k = line[2]
        if k == "D": D.append(json.loads(line)[1])
        elif k == "F": F.append(json.loads(line)[1])
        elif line.startswith('["SLOTS'): SL = {int(a): b for a, b in json.loads(line)[1].items()}
    M = collections.defaultdict(list)
    for r in F:
        for m in set(r["mints"]) | {e[0] for e in r["ev"]}: M[m].append(r)
    for m in M: M[m].sort(key=lambda r: (r["s"], r["i"]))
    out = []
    for d in D:
        m = d["dm"]; de = d["ev"][d["j"]]
        pre_v = de[5] + de[2]; pre_t = de[6] - de[3]          # curve before the sell (approx: sol out incl. fees ignored)
        P0 = de[5] / de[6]; Ppre = pre_v / pre_t if pre_t > 0 else None
        L = LAUNCH.get(m)
        fol = []
        for r in M.get(m, []):
            if not ((d["s"], d["i"]) < (r["s"], r["i"]) <= (d["s"] + 3, 10**6)): continue
            e = trade_of(r, m)
            fol.append([r["s"] - d["s"], r["i"], r["sg"], 0 if not r["err"] else r["err"], 1 if ((e[1] == 1) if e else is_buy_attempt(r, m)) else 0,
                        round(e[2] / 1e9, 4) if e else None, round((e[5] / e[6]) / P0, 5) if e else None, relays(r), tipsum(r), r["cup"], r["cul"], r["fee"],
                        r["progs"][:3], e[4] if e else None, r["sig"][:16]])
        out.append(dict(m=m, s=d["s"], i=d["i"], j=d["j"], sig=d["sig"][:16], sg=d["sg"], user=de[4], sol=round(de[2] / 1e9, 4), vsol=de[5], vtok=de[6],
                        drop=round(1 - P0 / Ppre, 4) if Ppre else None, relays=relays(d), tip=tipsum(d), cup=d["cup"],
                        age_s=round((d["s"] - L[0]) * 0.212, 1) if L else None, creator=(L[2] == de[4]) if L else None,
                        blk=SL.get(d["s"], [None, None]), blk1=SL.get(d["s"] + 1, [None, None]), fol=fol))
    return out
if __name__ == "__main__":
    fs = chunks(RUN)
    n = 0
    with gzip.open(OUTP, "wt", compresslevel=3) as w, Pool(4) as p:
        for res in p.imap(work, fs):
            for r in res: w.write(json.dumps(r, separators=(",", ":")) + "\n"); n += 1
    print("DONE", len(fs), n)
